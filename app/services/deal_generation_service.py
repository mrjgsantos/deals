from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.enums import DealStatus, ReviewStatus, ReviewType
from app.db.models import Deal, PriceObservation, ProductSourceRecord, ReviewQueue, Source
from app.ingestion.amazon_identifiers import canonicalize_amazon_product_url
from app.pricing.aggregation import aggregate_price_history_for_variant
from app.pricing.fake_discount import analyze_fake_discount
from app.pricing.schemas import DealScoringInput
from app.pricing.scoring import classify_source_link_quality, score_deal
from app.services.tracked_product_service import ensure_tracked_product_for_source_record

MIN_PREVIOUS_PRICE_OBSERVATIONS_30D = 3
MIN_PREVIOUS_PRICE_OBSERVATIONS_90D = 3
MIN_PREVIOUS_PRICE_OBSERVATIONS_ALL_TIME = 4
AUTO_PUBLISH_QUALITY_THRESHOLD = 70
MEDIUM_CONFIDENCE_AUTO_PUBLISH_THRESHOLD = 70
BORDERLINE_REVIEW_THRESHOLD = 60
BORDERLINE_REVIEW_PRIORITY = 150
STANDARD_REVIEW_PRIORITY = 100

logger = logging.getLogger(__name__)


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
            logger.info(
                "deal_generation_skipped source=%s product_source_record_id=%s reason=missing_product_variant",
                source.slug,
                product_source_record.id,
            )
            return DealGenerationResult(deal=None, review_queue_item=None, eligible=False)

        current_price = price_observation.sale_price or price_observation.total_price
        if current_price is None:
            logger.info(
                "deal_generation_skipped source=%s product_source_record_id=%s product_variant_id=%s reason=missing_current_price",
                source.slug,
                product_source_record.id,
                product_source_record.product_variant_id,
            )
            return DealGenerationResult(deal=None, review_queue_item=None, eligible=False)

        aggregation = aggregate_price_history_for_variant(
            db,
            product_source_record.product_variant_id,
            now=price_observation.observed_at,
        )
        scoring_aggregation = self._aggregation_for_scoring(aggregation)
        previous_price = self._supported_previous_price(price_observation, aggregation)
        claimed_discount_percent = self._claimed_discount_percent(current_price, previous_price)
        fake_discount = analyze_fake_discount(
            current_price=current_price,
            claimed_old_price=previous_price,
            claimed_discount_percent=claimed_discount_percent,
            aggregation=scoring_aggregation,
        )
        source_link_quality = classify_source_link_quality(product_source_record.source_url)
        scored = score_deal(
            DealScoringInput(
                current_price=current_price,
                claimed_old_price=previous_price,
                aggregation=scoring_aggregation,
                fake_discount_analysis=fake_discount,
                title=product_source_record.source_title,
                source_category=product_source_record.source_category,
                is_featured=False,
                merchant_priority=0,
                source_priority=0,
                category_priority=0,
                source_link_quality=source_link_quality,
            )
        )

        if not scored.quality.promotable:
            logger.info(
                "deal_generation_not_promotable source=%s product_source_record_id=%s product_variant_id=%s quality_score=%s quality_reasons=%s reason=creating_pending_review_deal",
                source.slug,
                product_source_record.id,
                product_source_record.product_variant_id,
                scored.quality.score,
                scored.quality.reasons,
            )

        auto_publish = self._should_auto_publish(scored)
        savings_amount = previous_price - current_price if previous_price is not None else None
        deal = self._get_existing_deal(db, product_source_record)
        canonical_deal_url = canonicalize_amazon_product_url(product_source_record.source_url) or product_source_record.source_url
        published_at = datetime.now(timezone.utc) if auto_publish else None
        preserve_published = False
        if deal is None:
            deal = Deal(
                product_variant_id=product_source_record.product_variant_id,
                product_source_record_id=product_source_record.id,
                price_observation_id=price_observation.id,
                source_id=source.id,
                title=product_source_record.source_title,
                status=DealStatus.PUBLISHED if auto_publish else DealStatus.PENDING_REVIEW,
                currency=product_source_record.currency,
                current_price=current_price,
                previous_price=previous_price,
                savings_amount=savings_amount,
                savings_percent=claimed_discount_percent / Decimal("100") if claimed_discount_percent is not None else None,
                published_at=published_at,
                deal_url=canonical_deal_url,
                summary=product_source_record.source_description,
                metadata_json=self._deal_metadata(scored, fake_discount, aggregation, source_link_quality),
            )
            db.add(deal)
            db.flush()
        else:
            preserve_published = deal.status == DealStatus.PUBLISHED and deal.published_at is not None
            deal.product_variant_id = product_source_record.product_variant_id
            deal.price_observation_id = price_observation.id
            deal.title = product_source_record.source_title
            deal.status = DealStatus.PUBLISHED if auto_publish or preserve_published else DealStatus.PENDING_REVIEW
            deal.currency = product_source_record.currency
            deal.current_price = current_price
            deal.previous_price = previous_price
            deal.savings_amount = savings_amount
            deal.savings_percent = claimed_discount_percent / Decimal("100") if claimed_discount_percent is not None else None
            if auto_publish and deal.published_at is None:
                deal.published_at = published_at
            deal.deal_url = canonical_deal_url
            deal.summary = product_source_record.source_description
            deal.metadata_json = self._deal_metadata(scored, fake_discount, aggregation, source_link_quality)

        deal.metadata_json = self._merged_metadata(
            deal.metadata_json,
            {
                "publication_decision": self._publication_decision(
                    scored=scored,
                    auto_publish=auto_publish,
                    preserve_published=preserve_published,
                )
            },
        )
        review_queue_item = self._get_existing_review_queue_item(db, deal)
        review_action = "none"
        if auto_publish:
            if review_queue_item is not None:
                review_queue_item.product_source_record_id = product_source_record.id
                review_queue_item.status = ReviewStatus.RESOLVED
                review_queue_item.reason = "auto_published_deal"
                review_queue_item.payload = self._review_payload(deal)
                review_queue_item.resolved_at = published_at or datetime.now(timezone.utc)
                review_action = "resolved_existing_review"
            else:
                review_action = "auto_published_without_review"
            self._log_generation_decision(
                source=source,
                product_source_record=product_source_record,
                deal=deal,
                scored=scored,
                auto_publish=auto_publish,
                preserve_published=preserve_published,
                review_action=review_action,
            )
            self._ensure_tracked_product(db, product_source_record)
            return DealGenerationResult(deal=deal, review_queue_item=review_queue_item, eligible=True)

        if review_queue_item is None:
            review_queue_item = ReviewQueue(
                product_source_record_id=product_source_record.id,
                entity_type=ReviewType.DEAL_VALIDATION,
                entity_id=deal.id,
                status=ReviewStatus.PENDING,
                priority=self._review_priority(scored),
                reason="auto_generated_deal_review",
                payload=self._review_payload(deal),
            )
            db.add(review_queue_item)
            db.flush()
            review_action = "created_pending_review"
        else:
            review_queue_item.product_source_record_id = product_source_record.id
            review_queue_item.status = ReviewStatus.PENDING
            review_queue_item.priority = self._review_priority(scored)
            review_queue_item.reason = "auto_generated_deal_review"
            review_queue_item.payload = self._review_payload(deal)
            review_queue_item.resolved_at = None
            review_action = "updated_pending_review"

        self._log_generation_decision(
            source=source,
            product_source_record=product_source_record,
            deal=deal,
            scored=scored,
            auto_publish=auto_publish,
            preserve_published=preserve_published,
            review_action=review_action,
        )
        self._ensure_tracked_product(db, product_source_record)

        return DealGenerationResult(deal=deal, review_queue_item=review_queue_item, eligible=True)

    def _should_auto_publish(self, scored) -> bool:
        quality_score = scored.quality.score or 0
        if not scored.quality.promotable:
            return False
        confidence = scored.quality.confidence_level
        if confidence == "medium":
            return quality_score >= MEDIUM_CONFIDENCE_AUTO_PUBLISH_THRESHOLD
        return quality_score >= AUTO_PUBLISH_QUALITY_THRESHOLD

    def _review_priority(self, scored) -> int:
        quality_score = scored.quality.score or 0
        if quality_score >= BORDERLINE_REVIEW_THRESHOLD:
            return BORDERLINE_REVIEW_PRIORITY
        return STANDARD_REVIEW_PRIORITY

    def _supported_previous_price(
        self,
        price_observation: PriceObservation,
        aggregation,
    ) -> Decimal | None:
        current_price = price_observation.sale_price or price_observation.total_price
        if current_price is None:
            return None

        historical_baseline = self._historical_previous_price_baseline(
            current_price=current_price,
            aggregation=aggregation,
        )
        if historical_baseline is not None:
            return historical_baseline

        return None

    def _historical_previous_price_baseline(
        self,
        *,
        current_price: Decimal,
        aggregation,
    ) -> Decimal | None:
        if not self._has_supported_historical_baseline(aggregation):
            return None

        if aggregation.avg_30d is not None and aggregation.observation_count_30d >= MIN_PREVIOUS_PRICE_OBSERVATIONS_30D:
            if aggregation.avg_30d > current_price:
                return aggregation.avg_30d

        if aggregation.avg_90d is not None and aggregation.avg_90d > current_price:
            return aggregation.avg_90d

        return None

    def _has_supported_historical_baseline(self, aggregation) -> bool:
        if aggregation.observation_count_90d < MIN_PREVIOUS_PRICE_OBSERVATIONS_90D:
            return False
        if aggregation.observation_count_all_time < MIN_PREVIOUS_PRICE_OBSERVATIONS_ALL_TIME:
            return False
        return True

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

    def _deal_metadata(self, scored, fake_discount, aggregation, source_link_quality: str | None) -> dict:
        return {
            "quality_score": scored.quality.score,
            "quality_reasons": scored.quality.reasons,
            "confidence_level": scored.quality.confidence_level,
            "business_score": scored.business.score,
            "business_reasons": scored.business.reasons,
            "promotable": scored.quality.promotable,
            "fake_discount": fake_discount.is_fake_discount,
            "fake_discount_flags": [flag.code for flag in fake_discount.flags],
            "price_aggregation": {
                "avg_30d": str(aggregation.avg_30d) if aggregation.avg_30d is not None else None,
                "avg_90d": str(aggregation.avg_90d) if aggregation.avg_90d is not None else None,
                "min_90d": str(aggregation.min_90d) if aggregation.min_90d is not None else None,
                "max_90d": str(aggregation.max_90d) if aggregation.max_90d is not None else None,
                "all_time_min": str(aggregation.all_time_min) if aggregation.all_time_min is not None else None,
                "days_at_current_price": aggregation.days_at_current_price,
                "observation_count_30d": aggregation.observation_count_30d,
                "observation_count_90d": aggregation.observation_count_90d,
                "observation_count_all_time": aggregation.observation_count_all_time,
            },
            "source_link_quality": source_link_quality,
        }

    def _publication_decision(
        self,
        *,
        scored,
        auto_publish: bool,
        preserve_published: bool,
    ) -> dict:
        quality_score = scored.quality.score or 0
        confidence = scored.quality.confidence_level
        if preserve_published:
            reason = "preserved_existing_publication"
        elif auto_publish:
            reason = "auto_publish_threshold_met"
        elif confidence == "medium" and quality_score < MEDIUM_CONFIDENCE_AUTO_PUBLISH_THRESHOLD:
            reason = "medium_confidence_below_threshold"
        elif quality_score >= BORDERLINE_REVIEW_THRESHOLD:
            reason = "borderline_manual_review"
        else:
            reason = "quality_below_auto_publish_threshold"
        return {
            "quality_score": quality_score,
            "confidence_level": confidence,
            "auto_publish_threshold": AUTO_PUBLISH_QUALITY_THRESHOLD,
            "medium_confidence_threshold": MEDIUM_CONFIDENCE_AUTO_PUBLISH_THRESHOLD,
            "auto_publish": auto_publish,
            "preserve_published": preserve_published,
            "review_bucket": "borderline" if quality_score >= BORDERLINE_REVIEW_THRESHOLD else "standard",
            "reason": reason,
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

    def _ensure_tracked_product(self, db: Session, product_source_record: ProductSourceRecord) -> None:
        ensure_tracked_product_for_source_record(db, product_source_record)

    def _merged_metadata(self, existing: dict | None, updates: dict) -> dict:
        merged = dict(existing or {})
        merged.update(updates)
        return merged

    def _log_generation_decision(
        self,
        *,
        source: Source,
        product_source_record: ProductSourceRecord,
        deal: Deal,
        scored,
        auto_publish: bool,
        preserve_published: bool,
        review_action: str,
    ) -> None:
        publication_decision = (deal.metadata_json or {}).get("publication_decision", {})
        logger.info(
            "deal_generation_decision source=%s product_source_record_id=%s product_variant_id=%s deal_id=%s deal_status=%s quality_score=%s promotable=%s auto_publish=%s preserve_published=%s publication_reason=%s review_action=%s quality_reasons=%s",
            source.slug,
            product_source_record.id,
            product_source_record.product_variant_id,
            deal.id,
            deal.status.value,
            scored.quality.score,
            scored.quality.promotable,
            auto_publish,
            preserve_published,
            publication_decision.get("reason"),
            review_action,
            scored.quality.reasons,
        )
