from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select

from app.db.enums import DealStatus
from app.db.models import Deal, PriceObservation, ProductSourceRecord
from app.jobs.common import job_session, run_job
from app.pricing.aggregation import aggregate_price_history
from app.pricing.fake_discount import analyze_fake_discount
from app.pricing.schemas import DealScoringInput, PricePoint
from app.pricing.scoring import classify_source_link_quality, score_deal


def main() -> int:
    def _runner(logger):
        now = datetime.now(UTC)

        with job_session() as db:
            deals = db.scalars(
                select(Deal).where(Deal.status.in_([DealStatus.PENDING_REVIEW, DealStatus.APPROVED]))
            ).all()

            scored_count = 0
            skipped_count = 0
            failed_count = 0
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

                        scored = score_deal(
                            DealScoringInput(
                                current_price=deal.current_price,
                                claimed_old_price=deal.previous_price,
                                aggregation=aggregation,
                                fake_discount_analysis=fake_discount,
                                is_featured=deal.is_featured,
                                merchant_priority=0,
                                source_priority=0,
                                category_priority=0,
                                source_link_quality=classify_source_link_quality(deal.deal_url),
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
