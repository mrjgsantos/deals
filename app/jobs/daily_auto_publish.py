from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from app.db.enums import DealStatus
from app.db.models import Deal
from app.jobs.common import job_session, run_job
from app.services.deal_generation_service import AUTO_PUBLISH_QUALITY_THRESHOLD, MEDIUM_CONFIDENCE_AUTO_PUBLISH_THRESHOLD


def main() -> int:
    def _runner(logger):
        now = datetime.now(UTC)

        with job_session() as db:
            # Two populations:
            # 1. PENDING_REVIEW deals that now score above the auto-publish threshold.
            # 2. APPROVED deals missing published_at (human-approved before the fix,
            #    or approved via a path that didn't stamp the timestamp).
            pending_review_deals = db.scalars(
                select(Deal).where(Deal.status == DealStatus.PENDING_REVIEW)
            ).all()

            approved_unpublished_deals = db.scalars(
                select(Deal).where(
                    Deal.status == DealStatus.APPROVED,
                    Deal.published_at.is_(None),
                )
            ).all()

            published_count = 0
            skipped_count = 0
            failed_count = 0

            # Population 1: auto-promote PENDING_REVIEW deals that meet the threshold.
            for deal in pending_review_deals:
                try:
                    with db.begin_nested():
                        metadata = deal.metadata_json or {}
                        quality_score = metadata.get("quality_score") or 0
                        promotable = metadata.get("promotable", False)
                        fake_discount = metadata.get("fake_discount", False)
                        # Default "high" preserves backward-compat for deals scored before
                        # the confidence tier was introduced.
                        confidence_level = metadata.get("confidence_level", "high")

                        if not promotable or fake_discount or quality_score < AUTO_PUBLISH_QUALITY_THRESHOLD:
                            skipped_count += 1
                            continue

                        if confidence_level == "medium" and quality_score < MEDIUM_CONFIDENCE_AUTO_PUBLISH_THRESHOLD:
                            skipped_count += 1
                            continue

                        deal.status = DealStatus.PUBLISHED
                        deal.published_at = now
                        db.add(deal)
                        published_count += 1
                        logger.info(
                            "auto_publish_deal_published deal_id=%s quality_score=%s",
                            deal.id,
                            quality_score,
                        )
                except Exception:
                    failed_count += 1
                    logger.exception("auto_publish_deal_failed deal_id=%s", deal.id)

            # Population 2: stamp published_at on APPROVED deals that are missing it.
            # No quality check — a human already approved these.
            for deal in approved_unpublished_deals:
                try:
                    with db.begin_nested():
                        deal.published_at = now
                        db.add(deal)
                        published_count += 1
                        logger.info(
                            "auto_publish_approved_deal_stamped deal_id=%s",
                            deal.id,
                        )
                except Exception:
                    failed_count += 1
                    logger.exception("auto_publish_approved_deal_failed deal_id=%s", deal.id)

            total = len(pending_review_deals) + len(approved_unpublished_deals)
            logger.info(
                "daily_auto_publish_complete pending_review=%s approved_unpublished=%s published=%s skipped=%s failed=%s",
                len(pending_review_deals),
                len(approved_unpublished_deals),
                published_count,
                skipped_count,
                failed_count,
            )
        return 0

    return run_job("daily_auto_publish", _runner)


if __name__ == "__main__":
    raise SystemExit(main())
