from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy.orm import Session

from app.db.enums import DealStatus, ReviewStatus, ReviewType, SourceType
from app.db.models import Deal, RawIngestionRecord, ReviewQueue, Source
from app.services.metrics_service import MetricsService


def test_metrics_service_overview_counts_duplicates_failures_and_published(db_session: Session) -> None:
    service = MetricsService()
    now = datetime.now(UTC)
    source_one = Source(
        name=f"Metrics Source One {uuid4().hex[:6]}",
        slug=f"metrics-source-one-{uuid4().hex[:8]}",
        source_type=SourceType.AFFILIATE_FEED,
        is_active=True,
    )
    source_two = Source(
        name=f"Metrics Source Two {uuid4().hex[:6]}",
        slug=f"metrics-source-two-{uuid4().hex[:8]}",
        source_type=SourceType.AFFILIATE_FEED,
        is_active=False,
    )
    db_session.add_all([source_one, source_two])
    db_session.flush()

    db_session.add_all(
        [
            RawIngestionRecord(
                source_id=source_one.id,
                parser_name="keepa",
                external_id=f"accepted-{uuid4().hex[:6]}",
                status="accepted",
                raw_payload={},
            ),
            RawIngestionRecord(
                source_id=source_one.id,
                parser_name="keepa",
                external_id=f"duplicate-{uuid4().hex[:6]}",
                status="duplicate",
                raw_payload={},
            ),
            RawIngestionRecord(
                source_id=source_one.id,
                parser_name="keepa",
                external_id=f"failed-{uuid4().hex[:6]}",
                status="failed",
                raw_payload={},
            ),
            RawIngestionRecord(
                source_id=source_two.id,
                parser_name="affiliate",
                external_id=f"rejected-{uuid4().hex[:6]}",
                status="rejected",
                raw_payload={},
            ),
        ]
    )

    published_deal = Deal(
        source_id=source_one.id,
        title="Published metrics deal",
        status=DealStatus.PUBLISHED,
        currency="EUR",
        current_price=Decimal("49.99"),
        detected_at=now,
        published_at=now,
    )
    approved_deal = Deal(
        source_id=source_one.id,
        title="Approved metrics deal",
        status=DealStatus.APPROVED,
        currency="EUR",
        current_price=Decimal("59.99"),
        detected_at=now,
    )
    pending_deal = Deal(
        source_id=source_two.id,
        title="Pending metrics deal",
        status=DealStatus.PENDING_REVIEW,
        currency="EUR",
        current_price=Decimal("69.99"),
        detected_at=now,
    )
    rejected_deal = Deal(
        source_id=source_two.id,
        title="Rejected metrics deal",
        status=DealStatus.REJECTED,
        currency="EUR",
        current_price=Decimal("79.99"),
        detected_at=now,
    )
    db_session.add_all([published_deal, approved_deal, pending_deal, rejected_deal])
    db_session.flush()

    db_session.add(
        ReviewQueue(
            product_source_record_id=None,
            entity_type=ReviewType.DEAL_VALIDATION,
            entity_id=pending_deal.id,
            status=ReviewStatus.PENDING,
            priority=100,
            reason="auto_generated_deal_review",
            payload={},
        )
    )
    db_session.flush()

    overview = service.get_overview(db_session)

    assert overview.raw_ingestion_records_duplicate == 1
    assert overview.raw_ingestion_records_failed == 1
    assert overview.deals_published == 1

    by_slug = {item.source_slug: item for item in overview.breakdown_by_source}
    source_one_metrics = by_slug[source_one.slug]
    source_two_metrics = by_slug[source_two.slug]

    assert source_one_metrics.raw_ingestion_records_duplicate == 1
    assert source_one_metrics.raw_ingestion_records_failed == 1
    assert source_one_metrics.deals_published == 1
    assert source_two_metrics.raw_ingestion_records_rejected == 1
    assert source_two_metrics.review_queue_pending == 1
