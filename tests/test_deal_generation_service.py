from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4
from types import SimpleNamespace

from app.db.enums import AvailabilityStatus, DealStatus, ReviewStatus, ReviewType, SourceType
from app.db.models import Deal, PriceObservation, ProductSourceRecord, ReviewQueue, Source, TrackedProduct
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
        source_title="Logitech G435 Wireless Gaming Headset",
        source_description="Dry dog food",
        source_category="Tech",
        currency="EUR",
        availability_status=AvailabilityStatus.IN_STOCK,
        source_attributes={"asin": "B0CCEXAMPLE"},
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


def make_existing_deal(
    *,
    source: Source,
    product_source_record: ProductSourceRecord,
    price_observation: PriceObservation,
    status: DealStatus = DealStatus.PENDING_REVIEW,
    published_at: datetime | None = None,
) -> Deal:
    return Deal(
        id=uuid4(),
        product_variant_id=product_source_record.product_variant_id,
        product_source_record_id=product_source_record.id,
        price_observation_id=price_observation.id,
        source_id=source.id,
        title=product_source_record.source_title,
        status=status,
        currency=product_source_record.currency,
        current_price=price_observation.total_price,
        previous_price=None,
        savings_amount=None,
        savings_percent=None,
        published_at=published_at,
        deal_url=product_source_record.source_url,
        summary=product_source_record.source_description,
        metadata_json={},
    )


def make_existing_review(deal: Deal, product_source_record: ProductSourceRecord) -> ReviewQueue:
    return ReviewQueue(
        id=uuid4(),
        product_source_record_id=product_source_record.id,
        entity_type=ReviewType.DEAL_VALIDATION,
        entity_id=deal.id,
        status=ReviewStatus.PENDING,
        priority=100,
        reason="auto_generated_deal_review",
        payload={"deal_id": str(deal.id)},
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


def make_scored_result(*, quality_score: int, promotable: bool = True):
    return SimpleNamespace(
        quality=SimpleNamespace(
            score=quality_score,
            promotable=promotable,
            reasons=["strong_history_support"] if quality_score >= 65 else ["weak_discount_support"],
        ),
        business=SimpleNamespace(
            score=20,
            reasons=["merchant_priority"],
        ),
    )


def test_sync_deal_creates_pending_review_deal_and_review_queue(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.deal_generation_service.aggregate_price_history_for_variant",
        lambda db, product_variant_id, now=None: make_aggregation(),
    )
    monkeypatch.setattr(
        "app.services.deal_generation_service.score_deal",
        lambda scoring_input: make_scored_result(quality_score=60, promotable=True),
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
    assert deal.metadata_json["publication_decision"]["reason"] == "borderline_manual_review"
    assert review.entity_type == ReviewType.DEAL_VALIDATION
    assert review.priority == 150
    assert review.reason == "auto_generated_deal_review"


def test_sync_deal_auto_publishes_high_quality_promotable_deal(monkeypatch, caplog) -> None:
    aggregation = PriceAggregation(
        current_price=Decimal("59.99"),
        avg_30d=Decimal("89.99"),
        avg_90d=Decimal("92.99"),
        min_90d=Decimal("59.99"),
        max_90d=Decimal("109.99"),
        all_time_min=Decimal("59.99"),
        all_time_max=Decimal("119.99"),
        days_at_current_price=1,
        observation_count_30d=8,
        observation_count_90d=24,
        observation_count_all_time=40,
    )
    monkeypatch.setattr(
        "app.services.deal_generation_service.aggregate_price_history_for_variant",
        lambda db, product_variant_id, now=None: aggregation,
    )
    monkeypatch.setattr(
        "app.services.deal_generation_service.score_deal",
        lambda scoring_input: make_scored_result(quality_score=72, promotable=True),
    )
    service = DealGenerationService()
    db = FakeSession(scalar_results=[None, None])
    caplog.set_level("INFO", logger="app.services.deal_generation_service")

    result = service.sync_deal_for_source_record(
        db,
        source=make_source(),
        product_source_record=make_record(),
        price_observation=make_observation(),
    )

    deal = next(obj for obj in db.added if isinstance(obj, Deal))

    assert result.eligible is True
    assert result.review_queue_item is None
    assert deal.status.value == "published"
    assert deal.published_at is not None
    assert deal.metadata_json["publication_decision"]["reason"] == "auto_publish_threshold_met"
    assert not any(isinstance(obj, ReviewQueue) for obj in db.added)
    assert "deal_generation_decision" in caplog.text
    assert "auto_publish=True" in caplog.text
    assert "publication_reason=auto_publish_threshold_met" in caplog.text


def test_sync_deal_stores_canonical_amazon_deal_url(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.deal_generation_service.aggregate_price_history_for_variant",
        lambda db, product_variant_id, now=None: make_aggregation(),
    )
    monkeypatch.setattr(
        "app.services.deal_generation_service.score_deal",
        lambda scoring_input: make_scored_result(quality_score=60, promotable=True),
    )
    service = DealGenerationService()
    db = FakeSession(scalar_results=[None, None])
    record = make_record()
    record.source_url = "https://www.amazon.es/Example-Product/dp/B0TEST1234/ref=sr_1_1?tag=partner-21&psc=1"

    service.sync_deal_for_source_record(
        db,
        source=make_source(),
        product_source_record=record,
        price_observation=make_observation(),
    )

    deal = next(obj for obj in db.added if isinstance(obj, Deal))
    assert deal.deal_url == "https://www.amazon.es/dp/B0TEST1234"


def test_sync_deal_keeps_low_score_promotable_deal_in_pending_review(monkeypatch, caplog) -> None:
    aggregation = PriceAggregation(
        current_price=Decimal("59.99"),
        avg_30d=Decimal("69.99"),
        avg_90d=Decimal("72.99"),
        min_90d=Decimal("59.99"),
        max_90d=Decimal("79.99"),
        all_time_min=Decimal("59.99"),
        all_time_max=Decimal("89.99"),
        days_at_current_price=1,
        observation_count_30d=3,
        observation_count_90d=6,
        observation_count_all_time=10,
    )
    monkeypatch.setattr(
        "app.services.deal_generation_service.aggregate_price_history_for_variant",
        lambda db, product_variant_id, now=None: aggregation,
    )
    monkeypatch.setattr(
        "app.services.deal_generation_service.score_deal",
        lambda scoring_input: make_scored_result(quality_score=64, promotable=True),
    )
    service = DealGenerationService()
    db = FakeSession(scalar_results=[None, None])
    caplog.set_level("INFO", logger="app.services.deal_generation_service")

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
    assert deal.published_at is None
    assert deal.metadata_json["publication_decision"]["reason"] == "borderline_manual_review"
    assert deal.metadata_json["publication_decision"]["review_bucket"] == "borderline"
    assert review.status == ReviewStatus.PENDING
    assert review.priority == 150
    assert review.reason == "auto_generated_deal_review"
    assert "review_action=created_pending_review" in caplog.text


def test_sync_deal_does_not_auto_publish_score_below_strict_threshold(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.deal_generation_service.aggregate_price_history_for_variant",
        lambda db, product_variant_id, now=None: make_aggregation(),
    )
    monkeypatch.setattr(
        "app.services.deal_generation_service.score_deal",
        lambda scoring_input: make_scored_result(quality_score=69, promotable=True),
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
    assert deal.status == DealStatus.PENDING_REVIEW
    assert deal.metadata_json["publication_decision"]["auto_publish_threshold"] == 70
    assert review.priority == 150


def test_sync_deal_auto_publish_resolves_existing_pending_review_item(monkeypatch, caplog) -> None:
    aggregation = PriceAggregation(
        current_price=Decimal("59.99"),
        avg_30d=Decimal("89.99"),
        avg_90d=Decimal("92.99"),
        min_90d=Decimal("59.99"),
        max_90d=Decimal("109.99"),
        all_time_min=Decimal("59.99"),
        all_time_max=Decimal("119.99"),
        days_at_current_price=1,
        observation_count_30d=8,
        observation_count_90d=24,
        observation_count_all_time=40,
    )
    monkeypatch.setattr(
        "app.services.deal_generation_service.aggregate_price_history_for_variant",
        lambda db, product_variant_id, now=None: aggregation,
    )
    monkeypatch.setattr(
        "app.services.deal_generation_service.score_deal",
        lambda scoring_input: make_scored_result(quality_score=72, promotable=True),
    )
    source = make_source()
    record = make_record()
    observation = make_observation()
    existing_deal = make_existing_deal(
        source=source,
        product_source_record=record,
        price_observation=observation,
    )
    existing_review = make_existing_review(existing_deal, record)
    existing_tracked = TrackedProduct(
        id=uuid4(),
        asin="B0CCEXAMPLE",
        domain_id=1,
    )
    service = DealGenerationService()
    db = FakeSession(scalar_results=[existing_deal, existing_review, existing_tracked])
    caplog.set_level("INFO", logger="app.services.deal_generation_service")

    result = service.sync_deal_for_source_record(
        db,
        source=source,
        product_source_record=record,
        price_observation=observation,
    )

    assert result.eligible is True
    assert result.deal is existing_deal
    assert result.review_queue_item is existing_review
    assert existing_deal.status == DealStatus.PUBLISHED
    assert existing_deal.published_at is not None
    assert existing_deal.metadata_json["publication_decision"]["reason"] == "auto_publish_threshold_met"
    assert existing_review.status == ReviewStatus.RESOLVED
    assert existing_review.reason == "auto_published_deal"
    assert existing_review.resolved_at is not None
    assert not any(isinstance(obj, ReviewQueue) for obj in db.added)
    assert "review_action=resolved_existing_review" in caplog.text


def test_sync_deal_preserves_existing_publication_and_reopens_review_when_score_drops(monkeypatch, caplog) -> None:
    aggregation = PriceAggregation(
        current_price=Decimal("59.99"),
        avg_30d=Decimal("69.99"),
        avg_90d=Decimal("72.99"),
        min_90d=Decimal("59.99"),
        max_90d=Decimal("79.99"),
        all_time_min=Decimal("59.99"),
        all_time_max=Decimal("89.99"),
        days_at_current_price=1,
        observation_count_30d=3,
        observation_count_90d=6,
        observation_count_all_time=10,
    )
    monkeypatch.setattr(
        "app.services.deal_generation_service.aggregate_price_history_for_variant",
        lambda db, product_variant_id, now=None: aggregation,
    )
    monkeypatch.setattr(
        "app.services.deal_generation_service.score_deal",
        lambda scoring_input: make_scored_result(quality_score=64, promotable=True),
    )
    source = make_source()
    record = make_record()
    observation = make_observation()
    original_published_at = datetime(2026, 4, 7, tzinfo=timezone.utc)
    existing_deal = make_existing_deal(
        source=source,
        product_source_record=record,
        price_observation=observation,
        status=DealStatus.PUBLISHED,
        published_at=original_published_at,
    )
    existing_tracked = TrackedProduct(
        id=uuid4(),
        asin="B0CCEXAMPLE",
        domain_id=1,
    )
    service = DealGenerationService()
    db = FakeSession(scalar_results=[existing_deal, None, existing_tracked])
    caplog.set_level("INFO", logger="app.services.deal_generation_service")

    result = service.sync_deal_for_source_record(
        db,
        source=source,
        product_source_record=record,
        price_observation=observation,
    )

    review = next(obj for obj in db.added if isinstance(obj, ReviewQueue))

    assert result.eligible is True
    assert result.deal is existing_deal
    assert result.review_queue_item is review
    assert existing_deal.status == DealStatus.PUBLISHED
    assert existing_deal.published_at == original_published_at
    assert existing_deal.metadata_json["publication_decision"]["reason"] == "preserved_existing_publication"
    assert existing_deal.metadata_json["publication_decision"]["preserve_published"] is True
    assert review.status == ReviewStatus.PENDING
    assert review.reason == "auto_generated_deal_review"
    assert review.entity_id == existing_deal.id
    assert "preserve_published=True" in caplog.text
    assert "review_action=created_pending_review" in caplog.text


def test_sync_deal_tracks_asin_when_deal_is_created(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.deal_generation_service.aggregate_price_history_for_variant",
        lambda db, product_variant_id, now=None: make_aggregation(),
    )
    monkeypatch.setattr(
        "app.services.deal_generation_service.score_deal",
        lambda scoring_input: make_scored_result(quality_score=60, promotable=True),
    )
    service = DealGenerationService()
    db = FakeSession(scalar_results=[None, None, None])

    result = service.sync_deal_for_source_record(
        db,
        source=make_source(),
        product_source_record=make_record(),
        price_observation=make_observation(),
    )

    tracked = next(obj for obj in db.added if isinstance(obj, TrackedProduct))

    assert result.eligible is True
    assert tracked.asin == "B0CCEXAMPLE"
    assert tracked.domain_id == 1


def test_sync_deal_does_not_duplicate_tracked_asin(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.deal_generation_service.aggregate_price_history_for_variant",
        lambda db, product_variant_id, now=None: make_aggregation(),
    )
    monkeypatch.setattr(
        "app.services.deal_generation_service.score_deal",
        lambda scoring_input: make_scored_result(quality_score=60, promotable=True),
    )
    existing_tracked = TrackedProduct(
        id=uuid4(),
        asin="B0CCEXAMPLE",
        domain_id=1,
    )
    service = DealGenerationService()
    db = FakeSession(scalar_results=[None, None, existing_tracked])

    service.sync_deal_for_source_record(
        db,
        source=make_source(),
        product_source_record=make_record(),
        price_observation=make_observation(),
    )

    assert not any(isinstance(obj, TrackedProduct) for obj in db.added)


def test_sync_deal_skips_non_promotable_records(monkeypatch, caplog) -> None:
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
    caplog.set_level("INFO", logger="app.services.deal_generation_service")
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
    assert "deal_generation_skipped" in caplog.text
    assert "reason=not_promotable" in caplog.text


def test_sync_deal_uses_supported_historical_baseline_for_previous_price(monkeypatch) -> None:
    aggregation = PriceAggregation(
        current_price=Decimal("59.99"),
        avg_30d=Decimal("89.99"),
        avg_90d=Decimal("92.99"),
        min_90d=Decimal("59.99"),
        max_90d=Decimal("109.99"),
        all_time_min=Decimal("59.99"),
        all_time_max=Decimal("119.99"),
        days_at_current_price=1,
        observation_count_30d=8,
        observation_count_90d=24,
        observation_count_all_time=40,
    )
    monkeypatch.setattr(
        "app.services.deal_generation_service.aggregate_price_history_for_variant",
        lambda db, product_variant_id, now=None: aggregation,
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

    assert result.eligible is True
    assert deal.previous_price == Decimal("89.99")
    assert deal.savings_amount == Decimal("30.00")
    assert deal.savings_percent == Decimal("0.3334")


def test_sync_deal_populates_savings_fields_with_minimally_acceptable_history(monkeypatch) -> None:
    aggregation = PriceAggregation(
        current_price=Decimal("59.99"),
        avg_30d=Decimal("69.99"),
        avg_90d=Decimal("71.99"),
        min_90d=Decimal("59.99"),
        max_90d=Decimal("79.99"),
        all_time_min=Decimal("59.99"),
        all_time_max=Decimal("79.99"),
        days_at_current_price=1,
        observation_count_30d=3,
        observation_count_90d=3,
        observation_count_all_time=4,
    )
    monkeypatch.setattr(
        "app.services.deal_generation_service.aggregate_price_history_for_variant",
        lambda db, product_variant_id, now=None: aggregation,
    )
    monkeypatch.setattr(
        "app.services.deal_generation_service.score_deal",
        lambda scoring_input: make_scored_result(quality_score=64, promotable=True),
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

    assert result.eligible is True
    assert deal.previous_price == Decimal("69.99")
    assert deal.savings_amount == Decimal("10.00")
    assert deal.savings_percent == Decimal("0.1429")


def test_sync_deal_keeps_previous_price_null_when_history_is_extremely_shallow(monkeypatch) -> None:
    aggregation = PriceAggregation(
        current_price=Decimal("59.99"),
        avg_30d=Decimal("89.99"),
        avg_90d=Decimal("92.99"),
        min_90d=Decimal("59.99"),
        max_90d=Decimal("109.99"),
        all_time_min=Decimal("59.99"),
        all_time_max=Decimal("119.99"),
        days_at_current_price=1,
        observation_count_30d=2,
        observation_count_90d=2,
        observation_count_all_time=3,
    )
    monkeypatch.setattr(
        "app.services.deal_generation_service.aggregate_price_history_for_variant",
        lambda db, product_variant_id, now=None: aggregation,
    )
    monkeypatch.setattr(
        "app.services.deal_generation_service.score_deal",
        lambda scoring_input: make_scored_result(quality_score=64, promotable=True),
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

    assert result.eligible is True
    assert deal.previous_price is None
    assert deal.savings_amount is None
    assert deal.savings_percent is None
