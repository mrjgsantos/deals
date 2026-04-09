from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.enums import DealStatus, ReviewStatus, ReviewType
from app.db.models import Deal, PriceObservation, ProductSourceRecord, ReviewQueue, Source
from app.pricing.aggregation import aggregate_price_history_for_variant
from app.pricing.fake_discount import analyze_fake_discount
from app.pricing.schemas import DealScoringInput
from app.pricing.scoring import score_deal


@dataclass(slots=True)
class DealGenerationResult:
    deal: Deal | None
    review_queue_item: ReviewQueue | None
    eligible: bool


class DealGenerationService:
    def sync_deal_for_source_record(
        self,
        db: Session,
        *,
        source: Source,
        product_source_record: ProductSourceRecord,
        price_observation: PriceObservation,
    ) -> DealGenerationResult:
        if product_source_record.product_variant_id is None:
            return DealGenerationResult(deal=None, review_queue_item=None, eligible=False)

        current_price = price_observation.sale_price or price_observation.total_price
        if current_price is None:
            return DealGenerationResult(deal=None, review_queue_item=None, eligible=False)

        aggregation = aggregate_price_history_for_variant(
            db,
            product_source_record.product_variant_id,
            now=price_observation.observed_at,
        )
        scoring_aggregation = self._aggregation_for_scoring(aggregation)
        previous_price = self._supported_previous_price(price_observation, aggregation.all_time_max)
        claimed_discount_percent = self._claimed_discount_percent(current_price, previous_price)
        fake_discount = analyze_fake_discount(
            current_price=current_price,
            claimed_old_price=previous_price,
            claimed_discount_percent=claimed_discount_percent,
            aggregation=scoring_aggregation,
        )
        scored = score_deal(
            DealScoringInput(
                current_price=current_price,
                claimed_old_price=previous_price,
                aggregation=scoring_aggregation,
                fake_discount_analysis=fake_discount,
                is_featured=False,
                merchant_priority=0,
                source_priority=0,
                category_priority=0,
            )
        )

        if not scored.quality.promotable:
            return DealGenerationResult(deal=None, review_queue_item=None, eligible=False)

        savings_amount = previous_price - current_price if previous_price is not None else None
        deal = self._get_existing_deal(db, product_source_record)
        if deal is None:
            deal = Deal(
                product_variant_id=product_source_record.product_variant_id,
                product_source_record_id=product_source_record.id,
                price_observation_id=price_observation.id,
                source_id=source.id,
                title=product_source_record.source_title,
                status=DealStatus.PENDING_REVIEW,
                currency=product_source_record.currency,
                current_price=current_price,
                previous_price=previous_price,
                savings_amount=savings_amount,
                savings_percent=claimed_discount_percent / Decimal("100") if claimed_discount_percent is not None else None,
                deal_url=product_source_record.source_url,
                summary=product_source_record.source_description,
                metadata_json=self._deal_metadata(scored, fake_discount, aggregation),
            )
            db.add(deal)
            db.flush()
        else:
            deal.product_variant_id = product_source_record.product_variant_id
            deal.price_observation_id = price_observation.id
            deal.title = product_source_record.source_title
            deal.status = DealStatus.PENDING_REVIEW
            deal.currency = product_source_record.currency
            deal.current_price = current_price
            deal.previous_price = previous_price
            deal.savings_amount = savings_amount
            deal.savings_percent = claimed_discount_percent / Decimal("100") if claimed_discount_percent is not None else None
            deal.deal_url = product_source_record.source_url
            deal.summary = product_source_record.source_description
            deal.metadata_json = self._deal_metadata(scored, fake_discount, aggregation)

        review_queue_item = self._get_existing_review_queue_item(db, deal)
        if review_queue_item is None:
            review_queue_item = ReviewQueue(
                product_source_record_id=product_source_record.id,
                entity_type=ReviewType.DEAL_VALIDATION,
                entity_id=deal.id,
                status=ReviewStatus.PENDING,
                priority=100,
                reason="auto_generated_deal_review",
                payload=self._review_payload(deal),
            )
            db.add(review_queue_item)
            db.flush()
        else:
            review_queue_item.product_source_record_id = product_source_record.id
            review_queue_item.status = ReviewStatus.PENDING
            review_queue_item.reason = "auto_generated_deal_review"
            review_queue_item.payload = self._review_payload(deal)

        return DealGenerationResult(deal=deal, review_queue_item=review_queue_item, eligible=True)

    def _supported_previous_price(
        self,
        price_observation: PriceObservation,
        all_time_max: Decimal | None,
    ) -> Decimal | None:
        if price_observation.list_price is None or price_observation.sale_price is None:
            return None
        if price_observation.list_price <= price_observation.sale_price:
            return None
        if all_time_max is None:
            return None
        if price_observation.list_price > all_time_max:
            return None
        return price_observation.list_price

    def _claimed_discount_percent(
        self,
        current_price: Decimal,
        previous_price: Decimal | None,
    ) -> Decimal | None:
        if previous_price is None or previous_price <= 0:
            return None
        return (((previous_price - current_price) / previous_price) * Decimal("100")).quantize(Decimal("0.01"))

    def _aggregation_for_scoring(self, aggregation):
        if aggregation.observation_count_all_time >= 2:
            return aggregation
        return replace(
            aggregation,
            avg_30d=None,
            avg_90d=None,
        )

    def _get_existing_deal(self, db: Session, product_source_record: ProductSourceRecord) -> Deal | None:
        return db.scalar(
            select(Deal).where(Deal.product_source_record_id == product_source_record.id)
        )

    def _get_existing_review_queue_item(self, db: Session, deal: Deal) -> ReviewQueue | None:
        return db.scalar(
            select(ReviewQueue).where(
                ReviewQueue.entity_type == ReviewType.DEAL_VALIDATION,
                ReviewQueue.entity_id == deal.id,
            )
        )

    def _deal_metadata(self, scored, fake_discount, aggregation) -> dict:
        return {
            "quality_score": scored.quality.score,
            "quality_reasons": scored.quality.reasons,
            "business_score": scored.business.score,
            "business_reasons": scored.business.reasons,
            "promotable": scored.quality.promotable,
            "fake_discount": fake_discount.is_fake_discount,
            "fake_discount_flags": [flag.code for flag in fake_discount.flags],
            "price_aggregation": {
                "avg_30d": str(aggregation.avg_30d) if aggregation.avg_30d is not None else None,
                "avg_90d": str(aggregation.avg_90d) if aggregation.avg_90d is not None else None,
                "min_90d": str(aggregation.min_90d) if aggregation.min_90d is not None else None,
                "all_time_min": str(aggregation.all_time_min) if aggregation.all_time_min is not None else None,
                "days_at_current_price": aggregation.days_at_current_price,
            },
        }

    def _review_payload(self, deal: Deal) -> dict:
        return {
            "deal_id": str(deal.id),
            "title": deal.title,
            "current_price": str(deal.current_price),
            "previous_price": str(deal.previous_price) if deal.previous_price is not None else None,
            "currency": deal.currency,
            "metadata": deal.metadata_json,
        }
