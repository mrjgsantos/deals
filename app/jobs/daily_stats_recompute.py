from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from app.db.enums import PriceStatisticWindow
from app.db.models import PriceObservation, PriceStatistic, ProductSourceRecord
from app.jobs.common import job_session, run_job
from app.pricing.aggregation import aggregate_price_history
from app.pricing.schemas import PricePoint


def main() -> int:
    def _runner(logger):
        today = datetime.now(UTC).date()

        with job_session() as db:
            pairs = db.execute(
                select(
                    ProductSourceRecord.product_variant_id,
                    ProductSourceRecord.source_id,
                )
                .join(PriceObservation, PriceObservation.product_source_record_id == ProductSourceRecord.id)
                .where(ProductSourceRecord.product_variant_id.is_not(None))
                .distinct()
            ).all()

        updated = 0
        failed = 0
        for pair in pairs:
            variant_id = pair.product_variant_id
            source_id = pair.source_id
            try:
                with job_session() as db:
                    rows = db.execute(
                        select(
                            PriceObservation.observed_at,
                            PriceObservation.sale_price,
                            PriceObservation.list_price,
                            PriceObservation.total_price,
                            PriceObservation.currency,
                        )
                        .join(ProductSourceRecord, PriceObservation.product_source_record_id == ProductSourceRecord.id)
                        .where(
                            ProductSourceRecord.product_variant_id == variant_id,
                            ProductSourceRecord.source_id == source_id,
                            PriceObservation.sale_price.is_not(None),
                        )
                        .order_by(PriceObservation.observed_at.asc())
                    ).all()

                    if not rows:
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
                        now=datetime.now(UTC),
                    )

                    statistic = db.scalar(
                        select(PriceStatistic).where(
                            PriceStatistic.product_variant_id == variant_id,
                            PriceStatistic.source_id == source_id,
                            PriceStatistic.statistic_window == PriceStatisticWindow.DAILY,
                            PriceStatistic.observed_on == today,
                        )
                    )

                    if statistic is None:
                        statistic = PriceStatistic(
                            product_variant_id=variant_id,
                            source_id=source_id,
                            statistic_window=PriceStatisticWindow.DAILY,
                            observed_on=today,
                            currency=rows[-1].currency,
                        )
                        db.add(statistic)

                    statistic.currency = rows[-1].currency
                    statistic.sample_count = aggregation.observation_count_90d
                    statistic.avg_price = aggregation.avg_30d
                    statistic.median_price = aggregation.avg_90d
                    statistic.min_price = aggregation.min_90d
                    statistic.max_price = aggregation.all_time_max
                    statistic.last_price = aggregation.current_price
                    statistic.metadata_json = {
                        "avg_30d": str(aggregation.avg_30d) if aggregation.avg_30d is not None else None,
                        "avg_90d": str(aggregation.avg_90d) if aggregation.avg_90d is not None else None,
                        "min_90d": str(aggregation.min_90d) if aggregation.min_90d is not None else None,
                        "all_time_min": str(aggregation.all_time_min) if aggregation.all_time_min is not None else None,
                        "all_time_max": str(aggregation.all_time_max) if aggregation.all_time_max is not None else None,
                        "days_at_current_price": aggregation.days_at_current_price,
                        "observation_count_all_time": aggregation.observation_count_all_time,
                    }
                updated += 1
            except Exception:
                failed += 1
                logger.exception(
                    "stats_recompute_pair_failed product_variant_id=%s source_id=%s",
                    variant_id,
                    source_id,
                )

        logger.info("stats_recompute_complete pairs=%s updated=%s failed=%s", len(pairs), updated, failed)
        return 0

    return run_job("daily_stats_recompute", _runner)


if __name__ == "__main__":
    raise SystemExit(main())
