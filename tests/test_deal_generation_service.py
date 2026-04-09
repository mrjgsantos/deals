from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from app.db.enums import AvailabilityStatus, ReviewType, SourceType
from app.db.models import Deal, PriceObservation, ProductSourceRecord, ReviewQueue, Source
from app.pricing.schemas import PriceAggregation
from app.services.deal_generation_service import DealGenerationService


class FakeSession:
    def __init__(self, scalar_results: list[object | None] | None = None):
        self.scalar_results = list(scalar_results or [])
        self.added: list[object] = []
        self.flush_count = 0

    def scalar(self, stmt):
        if self.scalar_results:
            return self.scalar_results.pop(0)
        return None

    def add(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = uuid4()
        self.added.append(obj)

    def flush(self):
        self.flush_count += 1

    @contextmanager
    def begin_nested(self):
        yield self


def make_source() -> Source:
    return Source(
        id=uuid4(),
        name="Amazon Keepa",
        slug="amazon-keepa",
        source_type=SourceType.AFFILIATE_FEED,
    )


def make_record() -> ProductSourceRecord:
    return ProductSourceRecord(
        id=uuid4(),
        source_id=uuid4(),
        product_variant_id=uuid4(),
        external_id="B0CCEXAMPLE",
        source_url="https://www.amazon.com/dp/B0CCEXAMPLE",
        source_title="Royal Canin Mini Adult 2x8kg",
        source_description="Dry dog food",
        currency="EUR",
        availability_status=AvailabilityStatus.IN_STOCK,
    )


def make_observation() -> PriceObservation:
    return PriceObservation(
        id=uuid4(),
        product_source_record_id=uuid4(),
        observed_at=datetime(2026, 4, 8, tzinfo=timezone.utc),
        currency="EUR",
        list_price=Decimal("79.99"),
        sale_price=Decimal("59.99"),
        total_price=Decimal("59.99"),
        in_stock=True,
        is_promotional=True,
        observed_hash="hash",
    )


def make_aggregation() -> PriceAggregation:
    return PriceAggregation(
        current_price=Decimal("59.99"),
        avg_30d=Decimal("59.99"),
        avg_90d=Decimal("59.99"),
        min_90d=Decimal("59.99"),
        max_90d=Decimal("59.99"),
        all_time_min=Decimal("59.99"),
        all_time_max=Decimal("59.99"),
        days_at_current_price=1,
        observation_count_30d=1,
        observation_count_90d=1,
        observation_count_all_time=1,
    )


def test_sync_deal_creates_pending_review_deal_and_review_queue(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.deal_generation_service.aggregate_price_history_for_variant",
        lambda db, product_variant_id, now=None: make_aggregation(),
    )
    service = DealGenerationService()
    db = FakeSession(scalar_results=[None, None])

    result = service.sync_deal_for_source_record(
        db,
        source=make_source(),
        product_source_record=make_record(),
        price_observation=make_observation(),
    )

    deal = next(obj for obj in db.added if isinstance(obj, Deal))
    review = next(obj for obj in db.added if isinstance(obj, ReviewQueue))

    assert result.eligible is True
    assert deal.status.value == "pending_review"
    assert deal.previous_price is None
    assert deal.metadata_json["promotable"] is True
    assert review.entity_type == ReviewType.DEAL_VALIDATION
    assert review.reason == "auto_generated_deal_review"


def test_sync_deal_skips_non_promotable_records(monkeypatch) -> None:
    aggregation = PriceAggregation(
        current_price=Decimal("105.00"),
        avg_30d=Decimal("95.00"),
        avg_90d=Decimal("95.00"),
        min_90d=Decimal("70.00"),
        max_90d=Decimal("110.00"),
        all_time_min=Decimal("65.00"),
        all_time_max=Decimal("120.00"),
        days_at_current_price=30,
        observation_count_30d=20,
        observation_count_90d=50,
        observation_count_all_time=120,
    )
    monkeypatch.setattr(
        "app.services.deal_generation_service.aggregate_price_history_for_variant",
        lambda db, product_variant_id, now=None: aggregation,
    )
    service = DealGenerationService()
    db = FakeSession()
    observation = make_observation()
    observation.sale_price = Decimal("105.00")
    observation.total_price = Decimal("105.00")
    observation.list_price = Decimal("150.00")

    result = service.sync_deal_for_source_record(
        db,
        source=make_source(),
        product_source_record=make_record(),
        price_observation=observation,
    )

    assert result.eligible is False
    assert not any(isinstance(obj, Deal) for obj in db.added)
