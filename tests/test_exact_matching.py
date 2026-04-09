from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from uuid import uuid4

from app.db.enums import AvailabilityStatus
from app.ingestion.schemas import NormalizedIngestionRecord
from app.matching.repository import ExactMatchCandidate
from app.matching.service import ExactMatchingService


class FakeExactMatchRepository:
    def __init__(self) -> None:
        self.by_gtin: dict[str, list[ExactMatchCandidate]] = {}
        self.by_asin: dict[str, list[ExactMatchCandidate]] = {}
        self.by_mpn_brand: dict[tuple[str, str], list[ExactMatchCandidate]] = {}

    def find_by_gtin(self, db, gtin: str) -> list[ExactMatchCandidate]:
        return self.by_gtin.get(gtin, [])

    def find_by_asin(self, db, asin: str) -> list[ExactMatchCandidate]:
        return self.by_asin.get(asin, [])

    def find_by_mpn_brand(self, db, mpn: str, brand: str) -> list[ExactMatchCandidate]:
        return self.by_mpn_brand.get((mpn, brand.casefold()), [])


def make_normalized_record(**overrides) -> NormalizedIngestionRecord:
    payload = {
        "normalized_name": "Royal Canin Mini Adult 2x8kg",
        "variant_key": "pack:2|weight:8:kg|bundle:false",
        "product_url": "https://example.com/p/royal-canin",
        "external_id": "external-1",
        "brand": "Royal Canin",
        "category": "Pet Food",
        "description": "Dog food",
        "image_url": "https://example.com/image.jpg",
        "merchant_name": "Example Store",
        "merchant_slug": "example-store",
        "currency": "EUR",
        "current_price": Decimal("59.99"),
        "list_price": Decimal("69.99"),
        "shipping_price": None,
        "total_price": Decimal("59.99"),
        "availability_status": AvailabilityStatus.IN_STOCK,
        "source_title": "Royal Canin Mini Adult 2x8kg",
        "source_brand": "Royal Canin",
        "source_description": "Dog food",
        "source_category": "Pet Food",
        "source_attributes": {
            "gtin": "0123456789012",
            "asin": "B0TESTASIN",
            "mpn": "RC-MINI-ADULT",
            "variant_parse": {
                "confidence": 0.5,
                "matched_rules": ["pack_x_measure"],
            },
        },
        "raw_payload": {},
        "observed_at": "2026-04-08T12:00:00Z",
        "pack_count": 2,
        "quantity": None,
        "quantity_unit": None,
        "weight": Decimal("8"),
        "weight_unit": "kg",
        "volume": None,
        "volume_unit": None,
        "size": None,
        "color": None,
        "material": None,
        "is_bundle": False,
    }
    payload.update(overrides)
    return NormalizedIngestionRecord(**payload)


def make_candidate(**overrides) -> ExactMatchCandidate:
    candidate = ExactMatchCandidate(
        product_id=uuid4(),
        product_variant_id=uuid4(),
        product_source_record_id=uuid4(),
        brand="Royal Canin",
        gtin="0123456789012",
        mpn="RC-MINI-ADULT",
        asin="B0TESTASIN",
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
    return replace(candidate, **overrides)


def test_match_by_gtin_when_variant_is_compatible() -> None:
    repository = FakeExactMatchRepository()
    candidate = make_candidate()
    repository.by_gtin["0123456789012"] = [candidate]
    service = ExactMatchingService(repository=repository)

    decision = service.match_normalized_record(db=None, normalized_record=make_normalized_record())

    assert decision.matched is True
    assert decision.match_key == "gtin"
    assert decision.product_variant_id == str(candidate.product_variant_id)


def test_do_not_match_by_gtin_when_pack_count_conflicts() -> None:
    repository = FakeExactMatchRepository()
    repository.by_gtin["0123456789012"] = [make_candidate(pack_count=1)]
    service = ExactMatchingService(repository=repository)

    decision = service.match_normalized_record(db=None, normalized_record=make_normalized_record())

    assert decision.matched is False
    assert decision.reason == "all exact matches blocked by critical variant conflict"


def test_do_not_match_by_asin_when_size_conflicts() -> None:
    repository = FakeExactMatchRepository()
    repository.by_gtin = {}
    repository.by_asin["B0TESTASIN"] = [make_candidate(gtin=None, size="24cm")]
    service = ExactMatchingService(repository=repository)

    record = make_normalized_record(
        source_title="Le Creuset 28cm",
        normalized_name="Le Creuset 28cm",
        source_attributes={
            "asin": "B0TESTASIN",
            "variant_parse": {"confidence": 0.17, "matched_rules": ["size_dimension"]},
        },
        pack_count=None,
        weight=None,
        weight_unit=None,
        size="28cm",
    )

    decision = service.match_normalized_record(db=None, normalized_record=record)

    assert decision.matched is False
    assert "critical variant conflict" in decision.blocked_reasons[0]


def test_match_by_mpn_plus_brand_when_no_gtin_or_asin() -> None:
    repository = FakeExactMatchRepository()
    candidate = make_candidate(gtin=None, asin=None)
    repository.by_mpn_brand[("RC-MINI-ADULT", "royal canin")] = [candidate]
    service = ExactMatchingService(repository=repository)

    record = make_normalized_record(
        source_attributes={
            "mpn": "RC-MINI-ADULT",
            "variant_parse": {"confidence": 0.5, "matched_rules": ["pack_x_measure"]},
        },
        brand="Royal Canin",
    )

    decision = service.match_normalized_record(db=None, normalized_record=record)

    assert decision.matched is True
    assert decision.match_key == "mpn_brand"


def test_ambiguous_exact_match_returns_no_match() -> None:
    repository = FakeExactMatchRepository()
    repository.by_gtin["0123456789012"] = [
        make_candidate(),
        make_candidate(),
    ]
    service = ExactMatchingService(repository=repository)

    decision = service.match_normalized_record(db=None, normalized_record=make_normalized_record())

    assert decision.matched is False
    assert decision.reason == "ambiguous exact match"


def test_no_exact_match_returns_separate_product_decision() -> None:
    repository = FakeExactMatchRepository()
    service = ExactMatchingService(repository=repository)

    decision = service.match_normalized_record(db=None, normalized_record=make_normalized_record())

    assert decision.matched is False
    assert decision.reason == "no exact match"
