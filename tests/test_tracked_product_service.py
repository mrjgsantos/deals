from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy.exc import OperationalError

from app.db.enums import AvailabilityStatus, DealStatus, SourceType
from app.db.models import Deal, PriceObservation, Product, ProductSourceRecord, ProductVariant, Source, TrackedProduct
from app.db.session import SessionLocal
from app.services.tracked_product_service import (
    TrackedProductOperationsService,
    ensure_tracked_product_for_source_record,
    get_active_tracked_asins,
)


class FakeScalarsResult:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class FakeSession:
    def __init__(self, rows):
        self.rows = rows
        self.added: list[object] = []

    def scalars(self, stmt):
        return FakeScalarsResult(self.rows)

    def scalar(self, stmt):
        return None

    def add(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = uuid4()
        self.added.append(obj)

    def flush(self):
        return None


def test_get_active_tracked_asins_returns_rows_from_tracked_pool() -> None:
    rows = [
        SimpleNamespace(id=uuid4(), asin="B0TEST1234", domain_id=9),
        SimpleNamespace(id=uuid4(), asin="B0TEST5678", domain_id=9),
    ]

    result = get_active_tracked_asins(FakeSession(rows), limit=100)

    assert [item.asin for item in result] == ["B0TEST1234", "B0TEST5678"]


def test_ensure_tracked_product_for_source_record_adds_new_row() -> None:
    db = FakeSession([])
    record = ProductSourceRecord(
        id=uuid4(),
        source_id=uuid4(),
        external_id="B0TEST1234",
        source_url="https://www.amazon.es/dp/B0TEST1234",
        source_title="Tracked product",
        currency="EUR",
        source_attributes={"asin": "B0TEST1234", "domain_id": 9},
    )

    tracked = ensure_tracked_product_for_source_record(db, record)

    assert tracked is not None
    assert tracked.asin == "B0TEST1234"
    assert tracked.domain_id == 9
    assert any(isinstance(item, TrackedProduct) for item in db.added)


def test_tracked_product_operations_service_surfaces_linked_metadata() -> None:
    service = TrackedProductOperationsService()
    asin = f"B0{uuid4().hex[:8].upper()}"
    now = datetime.now(UTC)

    try:
        with SessionLocal() as db:
            try:
                source = Source(
                    name=f"Amazon Keepa {uuid4().hex[:6]}",
                    slug=f"amazon-keepa-{uuid4().hex[:8]}",
                    source_type=SourceType.MARKETPLACE,
                )
                product = Product(normalized_name="Tracked product service item")
                variant = ProductVariant(product=product, variant_key=f"variant-{asin}")
                source_record = ProductSourceRecord(
                    source=source,
                    product=product,
                    product_variant=variant,
                    external_id=asin,
                    source_url=f"https://www.amazon.es/dp/{asin}",
                    source_title="Tracked Product Title",
                    currency="EUR",
                    availability_status=AvailabilityStatus.IN_STOCK,
                    source_attributes={"asin": asin, "domain_id": 9},
                    raw_payload={},
                )
                tracked_product = TrackedProduct(
                    asin=asin,
                    domain_id=9,
                    last_refresh_attempt_at=now,
                    last_refresh_succeeded_at=now,
                    last_refresh_status="succeeded",
                    next_refresh_eligible_at=now + timedelta(hours=24),
                )
                observation_one = PriceObservation(
                    product_source_record=source_record,
                    observed_at=now,
                    currency="EUR",
                    total_price=Decimal("59.99"),
                    observed_hash=f"obs-{uuid4().hex[:8]}",
                )
                observation_two = PriceObservation(
                    product_source_record=source_record,
                    observed_at=now,
                    currency="EUR",
                    total_price=Decimal("57.99"),
                    observed_hash=f"obs-{uuid4().hex[:8]}",
                )
                published_deal = Deal(
                    product_variant=variant,
                    product_source_record=source_record,
                    source=source,
                    title="Tracked published deal",
                    status=DealStatus.PUBLISHED,
                    currency="EUR",
                    current_price=Decimal("59.99"),
                    detected_at=now,
                    published_at=now,
                )
                pending_deal = Deal(
                    product_variant=variant,
                    product_source_record=source_record,
                    source=source,
                    title="Tracked pending deal",
                    status=DealStatus.PENDING_REVIEW,
                    currency="EUR",
                    current_price=Decimal("61.99"),
                    detected_at=now,
                )
                db.add_all(
                    [
                        source,
                        product,
                        variant,
                        source_record,
                        tracked_product,
                        observation_one,
                        observation_two,
                        published_deal,
                        pending_deal,
                    ]
                )
                db.flush()

                item = next(
                    record
                    for record in service.list_operations(db, limit=20, refresh_interval_seconds=600)
                    if record.asin == asin
                )

                assert item.display_name == "Tracked Product Title"
                assert item.source_slug == source.slug
                assert item.observation_count_all_time == 2
                assert item.linked_deal_count == 2
                assert item.has_pending_review_deal is True
                assert item.has_published_deal is True
                assert item.refresh_priority == "urgent"
                assert item.staleness_classification == "scheduled"
                assert item.consecutive_refresh_failures == 0
                assert item.next_refresh_earliest_at == now + timedelta(hours=24)
            finally:
                db.rollback()
    except OperationalError:
        pytest.skip("database unavailable")
