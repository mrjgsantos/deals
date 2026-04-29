"""
Daily deal expiry job.

Expires PUBLISHED and APPROVED deals whose current market price has risen
above the weighted historical baseline (60% avg_30d + 40% avg_90d) — the
same criterion daily_scoring uses to hard-reject a deal as
"price_above_historical_average".

Deals without a product_variant_id or without enough price history to
compute a baseline are skipped.
"""
from __future__ import annotations

import logging

from sqlalchemy import select

from app.db.enums import DealStatus
from app.db.models import Deal
from app.jobs.common import job_session, run_job
from app.pricing.aggregation import aggregate_price_history_for_variant
from app.pricing.scoring import compute_weighted_price_baseline


def main() -> int:
    def _runner(logger: logging.Logger) -> int:
        with job_session() as db:
            deals = db.scalars(
                select(Deal).where(
                    Deal.status.in_([DealStatus.PUBLISHED, DealStatus.APPROVED]),
                    Deal.product_variant_id.is_not(None),
                )
            ).all()

            total = len(deals)
            expired = 0
            skipped_no_baseline = 0
            skipped_price_ok = 0
            failed = 0

            for deal in deals:
                try:
                    with db.begin_nested():
                        agg = aggregate_price_history_for_variant(db, deal.product_variant_id)
                        baseline = compute_weighted_price_baseline(agg.avg_30d, agg.avg_90d)

                        if baseline is None:
                            skipped_no_baseline += 1
                            continue

                        if agg.current_price > baseline:
                            deal.status = DealStatus.EXPIRED
                            db.add(deal)
                            expired += 1
                            logger.info(
                                "deal_expiry_expired deal_id=%s current_price=%s baseline=%s",
                                deal.id,
                                agg.current_price,
                                baseline,
                            )
                        else:
                            skipped_price_ok += 1

                except Exception:
                    failed += 1
                    logger.exception("deal_expiry_failed deal_id=%s", deal.id)

            logger.info(
                "daily_deal_expiry_complete total=%s expired=%s skipped_no_baseline=%s skipped_price_ok=%s failed=%s",
                total,
                expired,
                skipped_no_baseline,
                skipped_price_ok,
                failed,
            )
        return 0

    return run_job("daily_deal_expiry", _runner)


if __name__ == "__main__":
    raise SystemExit(main())
