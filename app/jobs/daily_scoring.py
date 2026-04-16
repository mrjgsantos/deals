from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.db.enums import DealStatus
from app.db.models import Deal, PriceObservation, ProductSourceRecord
from app.jobs.common import job_session, run_job
from app.pricing.aggregation import aggregate_price_history
from app.pricing.fake_discount import analyze_fake_discount
from app.pricing.keyword_config import load_keyword_config
from app.pricing.schemas import DealScoringInput, PricePoint
from app.pricing.scoring import classify_source_link_quality, score_deal


def main() -> int:
    def _runner(logger):
        now = datetime.now(UTC)

        with job_session() as db:
            deals = db.scalars(
                select(Deal)
                .options(joinedload(Deal.product_source_record))
                .where(Deal.status.in_([DealStatus.PENDING_REVIEW, DealStatus.APPROVED]))
            ).all()

            keyword_config = load_keyword_config(db)

            # Build a lookup: product_variant_id -> days since most recent published deal.
            # Used to penalise deals for products promoted very recently.
            recency_window = now - timedelta(days=14)
            recent_rows = db.execute(
                select(Deal.product_variant_id, Deal.published_at)
                .where(
                    Deal.published_at.is_not(None),
                    Deal.published_at >= recency_window,
                    Deal.product_variant_id.is_not(None),
                )
            ).all()
            days_since_promoted: dict[UUID, int] = {}
            for pv_id, published_at in recent_rows:
                delta = int((now - published_at).total_seconds() // 86400)
                if pv_id not in days_since_promoted or delta < days_since_promoted[pv_id]:
                    days_since_promoted[pv_id] = delta

            scored_count = 0
            skipped_count = 0
            failed_count = 0
            logger.info("daily_scoring_starting deal_count=%s", len(deals))
            for deal in deals:
                try:
                    with db.begin_nested():
                        if deal.product_variant_id is None:
                            skipped_count += 1
                            continue

                        rows = db.execute(
                            select(
                                PriceObservation.observed_at,
                                PriceObservation.sale_price,
                                PriceObservation.list_price,
                                PriceObservation.total_price,
                            )
                            .join(ProductSourceRecord, PriceObservation.product_source_record_id == ProductSourceRecord.id)
                            .where(
                                ProductSourceRecord.product_variant_id == deal.product_variant_id,
                                PriceObservation.sale_price.is_not(None),
                            )
                            .order_by(PriceObservation.observed_at.asc())
                        ).all()

                        if not rows:
                            skipped_count += 1
                            continue

                        aggregation = aggregate_price_history(
                            [
                                PricePoint(
                                    observed_at=row.observed_at,
                                    sale_price=row.sale_price,
                                    list_price=row.list_price,
                                    total_price=row.total_price,
                                )
                                for row in rows
                            ],
                            now=now,
                        )

                        claimed_discount_percent = None
                        if deal.savings_percent is not None:
                            claimed_discount_percent = (
                                deal.savings_percent * Decimal("100")
                                if deal.savings_percent <= Decimal("1")
                                else deal.savings_percent
                            )

                        fake_discount = analyze_fake_discount(
                            current_price=deal.current_price,
                            claimed_old_price=deal.previous_price,
                            claimed_discount_percent=claimed_discount_percent,
                            aggregation=aggregation,
                        )

                        psr = deal.product_source_record
                        scored = score_deal(
                            DealScoringInput(
                                current_price=deal.current_price,
                                claimed_old_price=deal.previous_price,
                                aggregation=aggregation,
                                fake_discount_analysis=fake_discount,
                                title=deal.title,
                                source_category=psr.source_category if psr is not None else None,
                                is_featured=deal.is_featured,
                                merchant_priority=0,
                                source_priority=0,
                                category_priority=0,
                                source_link_quality=classify_source_link_quality(deal.deal_url),
                                keyword_config=keyword_config,
                                days_since_last_promoted=days_since_promoted.get(deal.product_variant_id),
                            )
                        )

                        deal.metadata_json = {
                            **(deal.metadata_json or {}),
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
                                "max_90d": str(aggregation.max_90d) if aggregation.max_90d is not None else None,
                                "all_time_min": str(aggregation.all_time_min) if aggregation.all_time_min is not None else None,
                                "days_at_current_price": aggregation.days_at_current_price,
                                "observation_count_30d": aggregation.observation_count_30d,
                                "observation_count_90d": aggregation.observation_count_90d,
                                "observation_count_all_time": aggregation.observation_count_all_time,
                            },
                            "source_link_quality": classify_source_link_quality(deal.deal_url),
                            "scored_at": now.isoformat(),
                        }
                    scored_count += 1
                except Exception:
                    failed_count += 1
                    logger.exception("daily_scoring_deal_failed deal_id=%s", deal.id)

            logger.info(
                "daily_scoring_complete deals=%s scored=%s skipped=%s failed=%s",
                len(deals),
                scored_count,
                skipped_count,
                failed_count,
            )
        return 0

    return run_job("daily_scoring", _runner)


if __name__ == "__main__":
    raise SystemExit(main())
