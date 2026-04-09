from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from app.db.enums import AvailabilityStatus, SourceType
from app.db.models import Merchant, PriceObservation, Product, ProductSourceRecord, ProductVariant, RawIngestionRecord, Source
from app.ingestion.exceptions import RecordRejectedError
from app.ingestion.interfaces import RecordNormalizer, SourceParser
from app.ingestion.schemas import NormalizedIngestionRecord, ParsedSourceRecord
from app.ingestion.service import IngestionService
from app.matching.service import MatchingService
from app.matching.types import MatchDecision


class FakeParser(SourceParser):
    parser_name = "fake"

    def __init__(self, records):
        self.records = records

    def parse(self, payload):
        return self.records


class FakeNormalizer(RecordNormalizer):
    def __init__(self, normalized_record: NormalizedIngestionRecord | None = None, error: Exception | None = None):
        self.normalized_record = normalized_record
        self.error = error

    def normalize(self, record: ParsedSourceRecord) -> NormalizedIngestionRecord:
        if self.error:
            raise self.error
        return self.normalized_record


class FakeSession:
    def __init__(self, scalar_result=None):
        self.scalar_result = scalar_result
        self.added = []
        self.committed = False
        self.flushed = 0

    def add(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = uuid4()
        self.added.append(obj)

    def flush(self):
        self.flushed += 1

    def commit(self):
        self.committed = True

    def scalar(self, stmt):
        return self.scalar_result

    @contextmanager
    def begin_nested(self):
        yield self


class StubIngestionService(IngestionService):
    def __init__(self, parser, normalizer, *, existing_observation=None, deal_generation_service=None, matcher=None):
        super().__init__(
            parser=parser,
            normalizer=normalizer,
            deal_generation_service=deal_generation_service,
            matcher=matcher or NoopMatcher(),
        )
        self.existing_observation = existing_observation

    def _get_source(self, db, source_slug: str) -> Source:
        return Source(
            id=uuid4(),
            name="Source",
            slug=source_slug,
            source_type=SourceType.AFFILIATE_FEED,
        )

    def _get_or_create_merchant(self, db, normalized):
        return Merchant(id=uuid4(), canonical_name="Merchant", slug="merchant")

    def _get_or_create_product_source_record(self, db, source, normalized):
        return ProductSourceRecord(
            id=uuid4(),
            source_id=source.id,
            external_id=normalized.external_id,
            source_title=normalized.source_title,
            currency=normalized.currency,
            availability_status=normalized.availability_status,
        )

    def _get_or_create_product(self, db, product_source_record, normalized, merchant, match_decision):
        return Product(
            id=uuid4(),
            merchant=merchant,
            normalized_name=normalized.normalized_name,
            brand=normalized.brand,
            category=normalized.category,
        )

    def _get_or_create_product_variant(self, db, product_source_record, product, normalized, match_decision):
        return ProductVariant(
            id=uuid4(),
            product=product,
            variant_key=normalized.variant_key,
            pack_count=normalized.pack_count,
            weight=normalized.weight,
            weight_unit=normalized.weight_unit,
            is_bundle=normalized.is_bundle,
        )

    def _create_or_reuse_price_observation(self, db, product_source_record, normalized, source_slug):
        if self.existing_observation is not None:
            return self.existing_observation, True
        observation = PriceObservation(
            id=uuid4(),
            product_source_record=product_source_record,
            observed_at=normalized.observed_at,
            currency=normalized.currency,
            sale_price=normalized.current_price,
            total_price=normalized.total_price,
            observed_hash=self._build_observed_hash(normalized, source_slug),
        )
        db.add(observation)
        return observation, False


def make_normalized_record() -> NormalizedIngestionRecord:
    return NormalizedIngestionRecord(
        normalized_name="Royal Canin Mini Adult 2x8kg",
        variant_key="pack:2|weight:8:kg|bundle:false",
        product_url="https://example.com/p/1",
        external_id="sku-1",
        brand="Royal Canin",
        category="Pet Food",
        description="Dog food",
        image_url="https://example.com/i.jpg",
        merchant_name="Example Store",
        merchant_slug="example-store",
        currency="EUR",
        current_price=Decimal("59.99"),
        list_price=Decimal("79.99"),
        shipping_price=None,
        total_price=Decimal("59.99"),
        availability_status=AvailabilityStatus.IN_STOCK,
        source_title="Royal Canin Mini Adult 2x8kg",
        source_brand="Royal Canin",
        source_description="Dog food",
        source_category="Pet Food",
        source_attributes={"gtin": "0123456789012"},
        raw_payload={"external_id": "sku-1"},
        observed_at=datetime(2026, 4, 8, tzinfo=timezone.utc),
        pack_count=2,
        quantity=None,
        quantity_unit=None,
        weight=Decimal("8"),
        weight_unit="kg",
        volume=None,
        volume_unit=None,
        size=None,
        color=None,
        material=None,
        is_bundle=False,
    )


def make_parsed_record() -> ParsedSourceRecord:
    return ParsedSourceRecord(
        external_id="sku-1",
        product_url="https://example.com/p/1",
        title="Royal Canin Mini Adult 2x8kg",
        brand="Royal Canin",
        currency="EUR",
        current_price=Decimal("59.99"),
        raw_payload={"external_id": "sku-1"},
    )


class RecordingDealGenerationService:
    def __init__(self) -> None:
        self.calls = []

    def sync_deal_for_source_record(self, db, *, source, product_source_record, price_observation):
        self.calls.append(
            {
                "source_id": source.id,
                "product_source_record_id": product_source_record.id,
                "price_observation_id": price_observation.id,
            }
        )


class NoopMatcher:
    def match_normalized_record(self, db, normalized_record):
        return MatchDecision(matched=False, reason="no match")


class StubMatcher:
    def __init__(self, decision: MatchDecision) -> None:
        self.decision = decision
        self.calls = 0

    def match_normalized_record(self, db, normalized_record):
        self.calls += 1
        return self.decision


class ExplodingMatcher:
    def match_normalized_record(self, db, normalized_record):
        raise AssertionError("matcher should not have been called")


class MatchAwareIngestionService(StubIngestionService):
    def _get_or_create_product(self, db, product_source_record, normalized, merchant, match_decision):
        product_id = uuid4()
        if match_decision.matched and match_decision.product_id:
            product_id = match_decision.product_id
        return Product(
            id=product_id,
            merchant=merchant,
            normalized_name=normalized.normalized_name,
            brand=normalized.brand,
            category=normalized.category,
        )

    def _get_or_create_product_variant(self, db, product_source_record, product, normalized, match_decision):
        variant_id = uuid4()
        if match_decision.matched and match_decision.product_variant_id:
            variant_id = match_decision.product_variant_id
        return ProductVariant(
            id=variant_id,
            product=product,
            variant_key=normalized.variant_key,
            pack_count=normalized.pack_count,
            weight=normalized.weight,
            weight_unit=normalized.weight_unit,
            is_bundle=normalized.is_bundle,
        )


def test_observed_hash_is_deterministic() -> None:
    normalized = make_normalized_record()
    service = StubIngestionService(FakeParser([]), FakeNormalizer(normalized))

    first = service._build_observed_hash(normalized, "source-a")
    second = service._build_observed_hash(normalized, "source-a")

    assert first == second


def test_duplicate_observation_is_reported_without_new_insert() -> None:
    normalized = make_normalized_record()
    existing = PriceObservation(
        id=uuid4(),
        product_source_record_id=uuid4(),
        observed_at=normalized.observed_at,
        currency=normalized.currency,
        sale_price=normalized.current_price,
        total_price=normalized.total_price,
        observed_hash="existing",
    )
    service = StubIngestionService(FakeParser([]), FakeNormalizer(normalized), existing_observation=existing)
    db = FakeSession()
    source = service._get_source(db, "source-a")
    raw_record = RawIngestionRecord(
        id=uuid4(),
        source_id=source.id,
        parser_name="fake",
        external_id="sku-1",
        raw_payload={"external_id": "sku-1"},
        status="pending",
    )

    result = service._persist_normalized_record(db, source, raw_record, normalized)

    assert result.status == "duplicate"
    assert result.price_observation_id == str(existing.id)
    assert raw_record.status == "duplicate"


def test_ingest_marks_rejected_records_without_aborting_batch() -> None:
    parsed_records = [make_parsed_record(), make_parsed_record()]
    parser = FakeParser(parsed_records)
    normalizer = FakeNormalizer(error=RecordRejectedError("missing current price"))
    service = StubIngestionService(parser, normalizer)
    db = FakeSession()

    result = service.ingest(db, "source-a", payload={})

    assert result.processed == 2
    assert result.rejected == 2
    assert [record.status for record in result.records] == ["rejected", "rejected"]


def test_ingest_triggers_deal_generation_after_persist() -> None:
    parsed_records = [make_parsed_record()]
    parser = FakeParser(parsed_records)
    normalizer = FakeNormalizer(make_normalized_record())
    deal_generation_service = RecordingDealGenerationService()
    service = StubIngestionService(
        parser,
        normalizer,
        deal_generation_service=deal_generation_service,
    )
    db = FakeSession()

    result = service.ingest(db, "source-a", payload={})

    assert result.accepted == 1
    assert len(deal_generation_service.calls) == 1


def test_ingest_uses_exact_match_and_skips_hybrid_when_exact_succeeds() -> None:
    normalized = make_normalized_record()
    exact_product_id = uuid4()
    exact_variant_id = uuid4()
    exact_matcher = StubMatcher(
        MatchDecision(
            matched=True,
            product_id=exact_product_id,
            product_variant_id=exact_variant_id,
            reason="exact match",
            match_strategy="exact",
        )
    )
    matcher = MatchingService(
        exact_matcher=exact_matcher,
        hybrid_matcher=ExplodingMatcher(),
    )
    service = MatchAwareIngestionService(
        FakeParser([make_parsed_record()]),
        FakeNormalizer(normalized),
        matcher=matcher,
    )
    db = FakeSession()

    result = service.ingest(db, "source-a", payload={})
    product_source_record = next(item for item in db.added if isinstance(item, ProductSourceRecord))

    assert result.accepted == 1
    assert exact_matcher.calls == 1
    assert product_source_record.product.id == exact_product_id
    assert product_source_record.product_variant.id == exact_variant_id


def test_ingest_uses_hybrid_match_when_exact_fails() -> None:
    normalized = make_normalized_record()
    hybrid_product_id = uuid4()
    hybrid_variant_id = uuid4()
    exact_matcher = StubMatcher(MatchDecision(matched=False, reason="no exact match"))
    hybrid_matcher = StubMatcher(
        MatchDecision(
            matched=True,
            product_id=hybrid_product_id,
            product_variant_id=hybrid_variant_id,
            reason="hybrid fallback auto-match",
            match_strategy="hybrid_fallback",
        )
    )
    matcher = MatchingService(
        exact_matcher=exact_matcher,
        hybrid_matcher=hybrid_matcher,
    )
    service = MatchAwareIngestionService(
        FakeParser([make_parsed_record()]),
        FakeNormalizer(normalized),
        matcher=matcher,
    )
    db = FakeSession()

    result = service.ingest(db, "source-a", payload={})
    product_source_record = next(item for item in db.added if isinstance(item, ProductSourceRecord))

    assert result.accepted == 1
    assert exact_matcher.calls == 1
    assert hybrid_matcher.calls == 1
    assert product_source_record.product.id == hybrid_product_id
    assert product_source_record.product_variant.id == hybrid_variant_id


def test_ingest_creates_new_variant_when_hybrid_returns_no_match() -> None:
    normalized = make_normalized_record()
    exact_matcher = StubMatcher(MatchDecision(matched=False, reason="no exact match"))
    hybrid_matcher = StubMatcher(
        MatchDecision(
            matched=False,
            reason="no hybrid auto-match",
            match_strategy="hybrid_fallback",
            candidate_product_variant_ids=["candidate-1"],
        )
    )
    matcher = MatchingService(
        exact_matcher=exact_matcher,
        hybrid_matcher=hybrid_matcher,
    )
    service = MatchAwareIngestionService(
        FakeParser([make_parsed_record()]),
        FakeNormalizer(normalized),
        matcher=matcher,
    )
    db = FakeSession()

    result = service.ingest(db, "source-a", payload={})
    product_source_record = next(item for item in db.added if isinstance(item, ProductSourceRecord))

    assert result.accepted == 1
    assert exact_matcher.calls == 1
    assert hybrid_matcher.calls == 1
    assert product_source_record.product.id not in {"candidate-1"}
    assert str(product_source_record.product_variant.id) not in {"candidate-1"}


def test_duplicate_observation_suppression_is_unchanged_with_matching_fallbacks() -> None:
    normalized = make_normalized_record()
    existing = PriceObservation(
        id=uuid4(),
        product_source_record_id=uuid4(),
        observed_at=normalized.observed_at,
        currency=normalized.currency,
        sale_price=normalized.current_price,
        total_price=normalized.total_price,
        observed_hash="existing",
    )
    matcher = MatchingService(
        exact_matcher=StubMatcher(MatchDecision(matched=False, reason="no exact match")),
        hybrid_matcher=StubMatcher(MatchDecision(matched=False, reason="no hybrid auto-match")),
    )
    service = MatchAwareIngestionService(
        FakeParser([make_parsed_record()]),
        FakeNormalizer(normalized),
        existing_observation=existing,
        matcher=matcher,
    )
    db = FakeSession()

    result = service.ingest(db, "source-a", payload={})

    assert result.accepted == 1
    assert result.records[0].status == "duplicate"
