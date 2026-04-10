from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.enums import DealStatus, ReviewStatus, ReviewType
from app.db.models import Deal, RawIngestionRecord, ReviewQueue, Source


@dataclass(slots=True)
class SourceMetricsRecord:
    source_id: UUID
    source_slug: str
    source_name: str
    is_active: bool
    raw_ingestion_records_total: int = 0
    raw_ingestion_records_accepted: int = 0
    raw_ingestion_records_rejected: int = 0
    raw_ingestion_records_duplicate: int = 0
    raw_ingestion_records_failed: int = 0
    deals_total: int = 0
    deals_pending_review: int = 0
    deals_approved: int = 0
    deals_rejected: int = 0
    deals_published: int = 0
    review_queue_pending: int = 0


@dataclass(slots=True)
class MetricsOverviewRecord:
    total_sources: int
    active_sources: int
    raw_ingestion_records_total: int
    raw_ingestion_records_recent: int
    raw_ingestion_records_accepted: int
    raw_ingestion_records_rejected: int
    raw_ingestion_records_duplicate: int
    raw_ingestion_records_failed: int
    deals_total: int
    deals_pending_review: int
    deals_approved: int
    deals_rejected: int
    deals_published: int
    review_queue_pending: int
    breakdown_by_source: list[SourceMetricsRecord] = field(default_factory=list)


class MetricsService:
    """Simple query-based operational metrics for the internal ops surface."""

    def get_overview(self, db: Session) -> MetricsOverviewRecord:
        recent_cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        source_rows = db.execute(
            select(Source.id, Source.slug, Source.name, Source.is_active).order_by(Source.name.asc(), Source.slug.asc())
        ).all()

        raw_counts_by_source = self._group_raw_ingestion_counts(db)
        deal_counts_by_source = self._group_deal_counts(db)
        pending_reviews_by_source = self._group_pending_review_counts(db)

        breakdown = [
            SourceMetricsRecord(
                source_id=source_id,
                source_slug=source_slug,
                source_name=source_name,
                is_active=is_active,
                raw_ingestion_records_total=raw_counts_by_source.get(source_id, {}).get("total", 0),
                raw_ingestion_records_accepted=raw_counts_by_source.get(source_id, {}).get("accepted", 0),
                raw_ingestion_records_rejected=raw_counts_by_source.get(source_id, {}).get("rejected", 0),
                raw_ingestion_records_duplicate=raw_counts_by_source.get(source_id, {}).get("duplicate", 0),
                raw_ingestion_records_failed=raw_counts_by_source.get(source_id, {}).get("failed", 0),
                deals_total=deal_counts_by_source.get(source_id, {}).get("total", 0),
                deals_pending_review=deal_counts_by_source.get(source_id, {}).get(DealStatus.PENDING_REVIEW.value, 0),
                deals_approved=deal_counts_by_source.get(source_id, {}).get(DealStatus.APPROVED.value, 0),
                deals_rejected=deal_counts_by_source.get(source_id, {}).get(DealStatus.REJECTED.value, 0),
                deals_published=deal_counts_by_source.get(source_id, {}).get(DealStatus.PUBLISHED.value, 0),
                review_queue_pending=pending_reviews_by_source.get(source_id, 0),
            )
            for source_id, source_slug, source_name, is_active in source_rows
        ]

        return MetricsOverviewRecord(
            total_sources=self._count(db, select(func.count(Source.id))),
            active_sources=self._count(db, select(func.count(Source.id)).where(Source.is_active.is_(True))),
            raw_ingestion_records_total=self._count(db, select(func.count(RawIngestionRecord.id))),
            raw_ingestion_records_recent=self._count(
                db,
                select(func.count(RawIngestionRecord.id)).where(RawIngestionRecord.created_at >= recent_cutoff),
            ),
            raw_ingestion_records_accepted=self._count(
                db,
                select(func.count(RawIngestionRecord.id)).where(RawIngestionRecord.status == "accepted"),
            ),
            raw_ingestion_records_rejected=self._count(
                db,
                select(func.count(RawIngestionRecord.id)).where(RawIngestionRecord.status == "rejected"),
            ),
            raw_ingestion_records_duplicate=self._count(
                db,
                select(func.count(RawIngestionRecord.id)).where(RawIngestionRecord.status == "duplicate"),
            ),
            raw_ingestion_records_failed=self._count(
                db,
                select(func.count(RawIngestionRecord.id)).where(RawIngestionRecord.status == "failed"),
            ),
            deals_total=self._count(db, select(func.count(Deal.id))),
            deals_pending_review=self._count(
                db,
                select(func.count(Deal.id)).where(Deal.status == DealStatus.PENDING_REVIEW),
            ),
            deals_approved=self._count(
                db,
                select(func.count(Deal.id)).where(Deal.status == DealStatus.APPROVED),
            ),
            deals_rejected=self._count(
                db,
                select(func.count(Deal.id)).where(Deal.status == DealStatus.REJECTED),
            ),
            deals_published=self._count(
                db,
                select(func.count(Deal.id)).where(Deal.status == DealStatus.PUBLISHED),
            ),
            review_queue_pending=self._count_pending_reviews(db),
            breakdown_by_source=breakdown,
        )

    def _count(self, db: Session, stmt) -> int:
        return int(db.scalar(stmt) or 0)

    def _count_pending_reviews(self, db: Session) -> int:
        stmt = (
            select(func.count(ReviewQueue.id))
            .join(Deal, Deal.id == ReviewQueue.entity_id)
            .where(
                ReviewQueue.entity_type == ReviewType.DEAL_VALIDATION,
                ReviewQueue.status == ReviewStatus.PENDING,
                Deal.status == DealStatus.PENDING_REVIEW,
            )
        )
        return self._count(db, stmt)

    def _group_raw_ingestion_counts(self, db: Session) -> dict[UUID, dict[str, int]]:
        rows = db.execute(
            select(
                RawIngestionRecord.source_id,
                RawIngestionRecord.status,
                func.count(RawIngestionRecord.id),
            ).group_by(RawIngestionRecord.source_id, RawIngestionRecord.status)
        ).all()
        grouped: dict[UUID, dict[str, int]] = {}
        for source_id, status, count in rows:
            source_counts = grouped.setdefault(
                source_id,
                {"total": 0, "accepted": 0, "rejected": 0, "duplicate": 0, "failed": 0},
            )
            source_counts["total"] += int(count)
            if status == "accepted":
                source_counts["accepted"] = int(count)
            elif status == "rejected":
                source_counts["rejected"] = int(count)
            elif status == "duplicate":
                source_counts["duplicate"] = int(count)
            elif status == "failed":
                source_counts["failed"] = int(count)
        return grouped

    def _group_deal_counts(self, db: Session) -> dict[UUID, dict[str, int]]:
        rows = db.execute(
            select(
                Deal.source_id,
                Deal.status,
                func.count(Deal.id),
            ).group_by(Deal.source_id, Deal.status)
        ).all()
        grouped: dict[UUID, dict[str, int]] = {}
        for source_id, status, count in rows:
            source_counts = grouped.setdefault(source_id, {"total": 0})
            source_counts["total"] += int(count)
            source_counts[status.value] = int(count)
        return grouped

    def _group_pending_review_counts(self, db: Session) -> dict[UUID, int]:
        rows = db.execute(
            select(
                Deal.source_id,
                func.count(ReviewQueue.id),
            )
            .join(Deal, Deal.id == ReviewQueue.entity_id)
            .where(
                ReviewQueue.entity_type == ReviewType.DEAL_VALIDATION,
                ReviewQueue.status == ReviewStatus.PENDING,
                Deal.status == DealStatus.PENDING_REVIEW,
            )
            .group_by(Deal.source_id)
        ).all()
        return {source_id: int(count) for source_id, count in rows}
