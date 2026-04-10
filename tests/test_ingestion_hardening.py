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


def updated_normalized_record(
    normalized: NormalizedIngestionRecord,
    **updates,
) -> NormalizedIngestionRecord:
    return NormalizedIngestionRecord.model_validate(
        {
            **normalized.model_dump(mode="python"),
            **updates,
        }
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


class ObservationAwareDealGenerationService:
    def __init__(self) -> None:
        self.observation_count_at_call = 0
        self.keepa_history_count_at_call = 0

    def sync_deal_for_source_record(self, db, *, source, product_source_record, price_observation):
        self.observation_count_at_call = sum(1 for item in db.added if isinstance(item, PriceObservation))
        self.keepa_history_count_at_call = sum(
            1
            for item in db.added
            if isinstance(item, PriceObservation) and (item.metadata_json or {}).get("derived_from") == "keepa_history"
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


class KeepaHistoryAwareIngestionService(StubIngestionService):
    def _find_existing_price_observation_by_hash(self, db, *, product_source_record_id, observed_hash):
        for item in db.added:
            if (
                isinstance(item, PriceObservation)
                and item.product_source_record_id == product_source_record_id
                and item.observed_hash == observed_hash
            ):
                return item
        return None


class KeepaFetchAwareIngestionService(KeepaHistoryAwareIngestionService):
    def __init__(
        self,
        parser,
        normalizer,
        *,
        keepa_payload=None,
        keepa_error: Exception | None = None,
        history_counts=(0, 0, 0),
        deal_generation_service=None,
        matcher=None,
    ):
        super().__init__(
            parser,
            normalizer,
            deal_generation_service=deal_generation_service,
            matcher=matcher,
        )
        self.keepa_payload = keepa_payload
        self.keepa_error = keepa_error
        self.history_counts = history_counts
        self.keepa_fetch_calls = []

    def _price_history_counts_for_variant(self, db, product_variant_id, *, now):
        return self.history_counts

    def _fetch_keepa_payload_for_asin(self, asin: str):
        self.keepa_fetch_calls.append(asin)
        if self.keepa_error is not None:
            raise self.keepa_error
        return self.keepa_payload


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


def test_ingest_keeps_exact_conflict_block_and_skips_hybrid() -> None:
    normalized = make_normalized_record()
    exact_matcher = StubMatcher(
        MatchDecision(
            matched=False,
            reason="all exact matches blocked by critical variant conflict",
            blocked_reasons=["critical variant conflict for gtin:0123456789012"],
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
    assert result.records[0].status == "accepted"
    assert product_source_record.product is not None
    assert product_source_record.product_variant is not None


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


def test_keepa_history_observations_are_inserted_when_keepa_payload_exists() -> None:
    normalized = make_normalized_record()
    normalized = updated_normalized_record(
        normalized,
        external_id="B0TEST1234",
        source_attributes={"asin": "B0TEST1234"},
        raw_payload={
            "data": {
                "NEW": [4999, 4599],
                "NEW_time": [0, 60],
            }
        },
        observed_at=datetime(2011, 1, 1, 3, 0, tzinfo=timezone.utc),
    )
    service = KeepaHistoryAwareIngestionService(
        FakeParser([make_parsed_record()]),
        FakeNormalizer(normalized),
    )
    db = FakeSession()

    result = service.ingest(db, "amazon-keepa", payload={})

    historical = [
        item
        for item in db.added
        if isinstance(item, PriceObservation) and (item.metadata_json or {}).get("derived_from") == "keepa_history"
    ]
    current = [
        item
        for item in db.added
        if isinstance(item, PriceObservation) and (item.metadata_json or {}).get("derived_from") != "keepa_history"
    ]

    assert result.accepted == 1
    assert len(current) == 1
    assert len(historical) == 2
    assert all(item.observed_at.year >= 2011 for item in historical)
    assert historical[0].sale_price == Decimal("49.99")
    assert historical[1].sale_price == Decimal("45.99")


def test_keepa_history_observations_fall_back_to_amazon_history_when_new_history_missing() -> None:
    normalized = make_normalized_record()
    normalized = updated_normalized_record(
        normalized,
        external_id="B0AMAZON123",
        source_attributes={"asin": "B0AMAZON123"},
        raw_payload={
            "data": {
                "AMAZON": [5599, 5199],
                "AMAZON_time": [0, 60],
            }
        },
        observed_at=datetime(2011, 1, 1, 3, 0, tzinfo=timezone.utc),
    )
    service = KeepaHistoryAwareIngestionService(
        FakeParser([make_parsed_record()]),
        FakeNormalizer(normalized),
    )
    db = FakeSession()

    result = service.ingest(db, "amazon-keepa", payload={})

    historical = [
        item
        for item in db.added
        if isinstance(item, PriceObservation) and (item.metadata_json or {}).get("derived_from") == "keepa_history"
    ]

    assert result.accepted == 1
    assert len(historical) == 2
    assert [item.sale_price for item in historical] == [Decimal("55.99"), Decimal("51.99")]


def test_duplicate_keepa_history_points_are_suppressed() -> None:
    normalized = make_normalized_record()
    normalized = updated_normalized_record(
        normalized,
        external_id="B0TEST1234",
        source_attributes={"asin": "B0TEST1234"},
        raw_payload={
            "data": {
                "NEW": [4999, 4999, 4599],
                "NEW_time": [0, 0, 60],
            }
        },
        observed_at=datetime(2011, 1, 1, 3, 0, tzinfo=timezone.utc),
    )
    service = KeepaHistoryAwareIngestionService(
        FakeParser([make_parsed_record()]),
        FakeNormalizer(normalized),
    )
    db = FakeSession()

    service.ingest(db, "amazon-keepa", payload={})

    historical = [
        item
        for item in db.added
        if isinstance(item, PriceObservation) and (item.metadata_json or {}).get("derived_from") == "keepa_history"
    ]

    assert len(historical) == 2


def test_ingestion_continues_when_keepa_history_enrichment_fails(monkeypatch) -> None:
    normalized = make_normalized_record()
    normalized = updated_normalized_record(
        normalized,
        external_id="B0TEST1234",
        source_attributes={"asin": "B0TEST1234"},
        raw_payload={"data": {"NEW": [4999], "NEW_time": [0]}},
    )
    service = KeepaHistoryAwareIngestionService(
        FakeParser([make_parsed_record()]),
        FakeNormalizer(normalized),
    )
    db = FakeSession()
    monkeypatch.setattr("app.ingestion.service.extract_keepa_price_points", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")))

    result = service.ingest(db, "amazon-keepa", payload={})

    current = [
        item
        for item in db.added
        if isinstance(item, PriceObservation) and (item.metadata_json or {}).get("derived_from") != "keepa_history"
    ]

    assert result.accepted == 1
    assert len(current) == 1


def test_current_observation_path_remains_intact_with_keepa_history() -> None:
    normalized = make_normalized_record()
    normalized = updated_normalized_record(
        normalized,
        external_id="B0TEST1234",
        source_attributes={"asin": "B0TEST1234"},
        raw_payload={
            "data": {
                "NEW": [4999],
                "NEW_time": [0],
            }
        },
        observed_at=datetime(2011, 1, 1, 2, 0, tzinfo=timezone.utc),
        current_price=Decimal("39.99"),
        total_price=Decimal("39.99"),
    )
    service = KeepaHistoryAwareIngestionService(
        FakeParser([make_parsed_record()]),
        FakeNormalizer(normalized),
    )
    db = FakeSession()

    result = service.ingest(db, "amazon-keepa", payload={})
    current = next(
        item
        for item in db.added
        if isinstance(item, PriceObservation) and (item.metadata_json or {}).get("derived_from") != "keepa_history"
    )

    assert result.records[0].price_observation_id == str(current.id)
    assert current.sale_price == Decimal("39.99")


def test_ingestion_with_keepa_enrichment_enabled_persists_history_before_deal_generation(caplog) -> None:
    normalized = updated_normalized_record(
        make_normalized_record(),
        product_url="https://www.amazon.es/dp/B0TEST1234",
        source_attributes={"asin": "B0TEST1234"},
        observed_at=datetime(2011, 1, 1, 3, 0, tzinfo=timezone.utc),
    )
    deal_generation_service = ObservationAwareDealGenerationService()
    service = KeepaFetchAwareIngestionService(
        FakeParser([make_parsed_record()]),
        FakeNormalizer(normalized),
        keepa_payload={
            "products": [
                {
                    "data": {
                        "NEW": [4999, 4599],
                        "NEW_time": [0, 60],
                    }
                }
            ]
        },
        history_counts=(1, 1, 1),
        deal_generation_service=deal_generation_service,
    )
    db = FakeSession()
    caplog.set_level("INFO", logger="app.ingestion.service")

    result = service.ingest(db, "serpapi-google-shopping", payload={})

    assert result.accepted == 1
    assert service.keepa_fetch_calls == ["B0TEST1234"]
    assert deal_generation_service.observation_count_at_call == 3
    assert deal_generation_service.keepa_history_count_at_call == 2
    assert "keepa_fetch_enrichment_due" in caplog.text
    assert "keepa_fetch_enrichment_complete" in caplog.text


def test_ingestion_without_asin_skips_keepa_fetch(caplog) -> None:
    normalized = updated_normalized_record(
        make_normalized_record(),
        product_url="https://www.amazon.es/dp/B0TEST1234",
        source_attributes={},
    )
    service = KeepaFetchAwareIngestionService(
        FakeParser([make_parsed_record()]),
        FakeNormalizer(normalized),
        keepa_error=AssertionError("keepa should not have been called"),
    )
    db = FakeSession()
    caplog.set_level("INFO", logger="app.ingestion.service")

    result = service.ingest(db, "serpapi-google-shopping", payload={})

    assert result.accepted == 1
    assert service.keepa_fetch_calls == []
    assert "keepa_fetch_enrichment_skipped" in caplog.text
    assert "reason=missing_asin" in caplog.text


def test_ingestion_continues_when_keepa_fetch_fails() -> None:
    normalized = updated_normalized_record(
        make_normalized_record(),
        product_url="https://www.amazon.es/dp/B0TEST1234",
        source_attributes={"asin": "B0TEST1234"},
    )
    service = KeepaFetchAwareIngestionService(
        FakeParser([make_parsed_record()]),
        FakeNormalizer(normalized),
        keepa_error=RuntimeError("boom"),
        history_counts=(1, 1, 1),
    )
    db = FakeSession()

    result = service.ingest(db, "serpapi-google-shopping", payload={})
    current = [
        item
        for item in db.added
        if isinstance(item, PriceObservation) and (item.metadata_json or {}).get("derived_from") != "keepa_history"
    ]

    assert result.accepted == 1
    assert service.keepa_fetch_calls == ["B0TEST1234"]
    assert len(current) == 1


def test_ingestion_with_sufficient_history_skips_keepa_fetch(caplog) -> None:
    normalized = updated_normalized_record(
        make_normalized_record(),
        product_url="https://www.amazon.es/dp/B0TEST1234",
        source_attributes={"asin": "B0TEST1234"},
    )
    service = KeepaFetchAwareIngestionService(
        FakeParser([make_parsed_record()]),
        FakeNormalizer(normalized),
        keepa_error=AssertionError("keepa should not have been called"),
        history_counts=(5, 8, 8),
    )
    db = FakeSession()
    caplog.set_level("INFO", logger="app.ingestion.service")

    result = service.ingest(db, "serpapi-google-shopping", payload={})

    assert result.accepted == 1
    assert service.keepa_fetch_calls == []
    assert "keepa_fetch_enrichment_skipped" in caplog.text
    assert "reason=sufficient_local_history" in caplog.text
