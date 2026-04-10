from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from uuid import uuid4

from app.db.enums import AvailabilityStatus
from app.ingestion.schemas import NormalizedIngestionRecord
from app.matching.decision import MatchDecision, has_critical_hard_gate, should_auto_match_hybrid, HybridDecisionInput
from app.matching.hybrid_service import HybridFallbackMatchingService
from app.matching.repository import HybridMatchCandidate
from app.matching.service import MatchingService


class FakeHybridMatchRepository:
    def __init__(self, candidates: list[HybridMatchCandidate]) -> None:
        self.candidates = candidates

    def find_candidates(self, db, *, brand: str | None, title_tokens: list[str], limit: int = 50) -> list[HybridMatchCandidate]:
        return self.candidates[:limit]


class StubExactMatcher:
    def __init__(self, decision: MatchDecision) -> None:
        self.decision = decision

    def match_normalized_record(self, db, normalized_record) -> MatchDecision:
        return self.decision


class StubHybridMatcher:
    def __init__(self, decision: MatchDecision) -> None:
        self.decision = decision

    def match_normalized_record(self, db, normalized_record) -> MatchDecision:
        return self.decision


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


def make_candidate(**overrides) -> HybridMatchCandidate:
    candidate = HybridMatchCandidate(
        product_id=uuid4(),
        product_variant_id=uuid4(),
        product_source_record_id=uuid4(),
        normalized_name="Royal Canin Mini Adult 2x8kg",
        brand="Royal Canin",
        category="Pet Food",
        source_title="Royal Canin Mini Adult 2x8kg",
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


def test_hybrid_auto_matches_same_product_with_different_title_formatting() -> None:
    candidate = make_candidate(
        normalized_name="Apple iPhone 15 Black 128GB",
        brand="Apple",
        category="Phones",
        source_title="Apple iPhone 15 Black 128GB",
        pack_count=None,
        weight=None,
        weight_unit=None,
        color="black",
    )
    service = HybridFallbackMatchingService(repository=FakeHybridMatchRepository([candidate]))

    decision = service.match_normalized_record(
        db=None,
        normalized_record=make_normalized_record(
            normalized_name="iPhone 15 128 GB Black",
            source_title="iPhone 15 128 GB Black",
            brand="Apple",
            source_brand="Apple",
            category="Phones",
            pack_count=None,
            weight=None,
            weight_unit=None,
            color="black",
            source_attributes={"variant_parse": {"confidence": 0.0, "matched_rules": []}},
        ),
    )

    assert decision.matched is True
    assert decision.match_strategy == "hybrid_fallback"
    assert decision.product_variant_id == str(candidate.product_variant_id)
    assert decision.confidence is not None and decision.confidence >= 0.85
    assert decision.debug is not None
    assert decision.debug.candidate_count_considered == 1
    assert decision.debug.top_candidate_score == decision.confidence
    assert decision.debug.top_candidate_lexical_score is not None
    assert decision.debug.final_decision_reason == "hybrid fallback auto-match"
    assert decision.debug.candidates[0].product_variant_id == str(candidate.product_variant_id)


def test_hybrid_auto_matches_same_product_with_language_title_variation() -> None:
    candidate = make_candidate(
        normalized_name="Apple iPhone 15 128GB Black",
        brand="Apple",
        category="Phones",
        source_title="Apple iPhone 15 128GB Black",
        pack_count=None,
        weight=None,
        weight_unit=None,
        color="black",
    )
    service = HybridFallbackMatchingService(repository=FakeHybridMatchRepository([candidate]))

    decision = service.match_normalized_record(
        db=None,
        normalized_record=make_normalized_record(
            normalized_name="iPhone 15 128 GB Preto Apple",
            source_title="iPhone 15 128 GB Preto Apple",
            brand="Apple",
            source_brand="Apple",
            category="Phones",
            pack_count=None,
            weight=None,
            weight_unit=None,
            color=None,
            source_attributes={"variant_parse": {"confidence": 0.0, "matched_rules": []}},
        ),
    )

    assert decision.matched is True
    assert decision.match_strategy == "hybrid_fallback"


def test_hybrid_returns_no_automatic_match_when_top_candidates_are_ambiguous() -> None:
    first = make_candidate(
        normalized_name="Apple AirPods Pro 2nd Gen",
        brand="Apple",
        category="Audio",
        source_title="Apple AirPods Pro 2nd Gen",
        pack_count=None,
        weight=None,
        weight_unit=None,
    )
    second = make_candidate(
        normalized_name="Apple AirPods Pro Gen 2",
        brand="Apple",
        category="Audio",
        source_title="Apple AirPods Pro Gen 2",
        pack_count=None,
        weight=None,
        weight_unit=None,
    )
    service = HybridFallbackMatchingService(repository=FakeHybridMatchRepository([first, second]))

    record = make_normalized_record(
        normalized_name="Apple AirPods Pro 2nd Gen",
        source_title="Apple AirPods Pro 2nd Gen",
        brand="Apple",
        source_brand="Apple",
        pack_count=None,
        weight=None,
        weight_unit=None,
        source_attributes={"variant_parse": {"confidence": 0.0, "matched_rules": []}},
    )

    decision = service.match_normalized_record(db=None, normalized_record=record)

    assert decision.matched is False
    assert decision.reason == "ambiguous hybrid match"
    assert len(decision.candidate_product_variant_ids) == 2


def test_hybrid_rejects_storage_conflicts() -> None:
    conflicting_candidate = make_candidate(
        normalized_name="Samsung Galaxy S24 128GB",
        brand="Samsung",
        category="Phones",
        source_title="Samsung Galaxy S24 128GB",
        pack_count=None,
        weight=None,
        weight_unit=None,
    )
    service = HybridFallbackMatchingService(repository=FakeHybridMatchRepository([conflicting_candidate]))

    record = make_normalized_record(
        normalized_name="Samsung Galaxy S24 256GB",
        source_title="Samsung Galaxy S24 256GB",
        brand="Samsung",
        source_brand="Samsung",
        category="Phones",
        pack_count=None,
        weight=None,
        weight_unit=None,
        source_attributes={"variant_parse": {"confidence": 0.0, "matched_rules": []}},
    )

    decision = service.match_normalized_record(db=None, normalized_record=record)

    assert decision.matched is False
    assert any("storage conflict" in reason for reason in decision.blocked_reasons)
    assert decision.reason == "hybrid fallback found only conflicting or weak candidates"


def test_hybrid_rejects_generation_conflicts() -> None:
    conflicting_candidate = make_candidate(
        normalized_name="Apple AirPods Pro 2nd Gen",
        brand="Apple",
        category="Audio",
        source_title="Apple AirPods Pro 2nd Gen",
        pack_count=None,
        weight=None,
        weight_unit=None,
    )
    service = HybridFallbackMatchingService(repository=FakeHybridMatchRepository([conflicting_candidate]))

    record = make_normalized_record(
        normalized_name="Apple AirPods Pro 3rd Gen",
        source_title="Apple AirPods Pro 3rd Gen",
        brand="Apple",
        source_brand="Apple",
        category="Audio",
        pack_count=None,
        weight=None,
        weight_unit=None,
        source_attributes={"variant_parse": {"confidence": 0.0, "matched_rules": []}},
    )

    decision = service.match_normalized_record(db=None, normalized_record=record)

    assert decision.matched is False
    assert any("generation conflict" in reason or "model conflict" in reason for reason in decision.blocked_reasons)


def test_hybrid_rejects_sony_model_family_mismatch() -> None:
    conflicting_candidate = make_candidate(
        normalized_name="Sony WH-1000XM4 Wireless Headphones",
        brand="Sony",
        category="Audio",
        source_title="Sony WH-1000XM4 Wireless Headphones",
        pack_count=None,
        weight=None,
        weight_unit=None,
    )
    service = HybridFallbackMatchingService(repository=FakeHybridMatchRepository([conflicting_candidate]))

    decision = service.match_normalized_record(
        db=None,
        normalized_record=make_normalized_record(
            normalized_name="Sony WH-1000XM5 Wireless Headphones",
            source_title="Sony WH-1000XM5 Wireless Headphones",
            brand="Sony",
            source_brand="Sony",
            category="Audio",
            pack_count=None,
            weight=None,
            weight_unit=None,
            source_attributes={"variant_parse": {"confidence": 0.0, "matched_rules": []}},
        ),
    )

    assert decision.matched is False
    assert any("model conflict" in reason for reason in decision.blocked_reasons)


def test_missing_color_does_not_block_hybrid_auto_match() -> None:
    candidate = make_candidate(
        normalized_name="Apple iPhone 15 128GB",
        brand="Apple",
        category="Phones",
        source_title="Apple iPhone 15 128GB",
        pack_count=None,
        weight=None,
        weight_unit=None,
        color=None,
    )
    service = HybridFallbackMatchingService(repository=FakeHybridMatchRepository([candidate]))

    decision = service.match_normalized_record(
        db=None,
        normalized_record=make_normalized_record(
            normalized_name="iPhone 15 128 GB Black",
            source_title="iPhone 15 128 GB Black",
            brand="Apple",
            source_brand="Apple",
            category="Phones",
            pack_count=None,
            weight=None,
            weight_unit=None,
            color="black",
            source_attributes={"variant_parse": {"confidence": 0.0, "matched_rules": []}},
        ),
    )

    assert decision.matched is True
    assert decision.match_strategy == "hybrid_fallback"


def test_missing_weak_attributes_do_not_count_as_conflicts() -> None:
    candidate = make_candidate(
        normalized_name="Apple iPhone 15 128GB",
        brand="Apple",
        category="Phones",
        source_title="Apple iPhone 15 128GB",
        pack_count=None,
        weight=None,
        weight_unit=None,
        color=None,
        material=None,
    )
    service = HybridFallbackMatchingService(repository=FakeHybridMatchRepository([candidate]))

    decision = service.match_normalized_record(
        db=None,
        normalized_record=make_normalized_record(
            normalized_name="iPhone 15 128 GB",
            source_title="iPhone 15 128 GB",
            brand="Apple",
            source_brand="Apple",
            category="Phones",
            pack_count=None,
            weight=None,
            weight_unit=None,
            color=None,
            material=None,
            source_attributes={"variant_parse": {"confidence": 0.0, "matched_rules": []}},
        ),
    )

    assert decision.matched is True
    assert decision.blocked_reasons == []


def test_incomplete_title_with_multiple_candidates_does_not_auto_match() -> None:
    first = make_candidate(
        normalized_name="Apple iPhone 15 128GB Black",
        brand="Apple",
        category="Phones",
        source_title="Apple iPhone 15 128GB Black",
        pack_count=None,
        weight=None,
        weight_unit=None,
        color="black",
    )
    second = make_candidate(
        normalized_name="Apple iPhone 15 256GB Black",
        brand="Apple",
        category="Phones",
        source_title="Apple iPhone 15 256GB Black",
        pack_count=None,
        weight=None,
        weight_unit=None,
        color="black",
    )
    service = HybridFallbackMatchingService(repository=FakeHybridMatchRepository([first, second]))

    decision = service.match_normalized_record(
        db=None,
        normalized_record=make_normalized_record(
            normalized_name="Apple iPhone 15",
            source_title="Apple iPhone 15",
            brand="Apple",
            source_brand="Apple",
            category="Phones",
            pack_count=None,
            weight=None,
            weight_unit=None,
            color=None,
            source_attributes={"variant_parse": {"confidence": 0.0, "matched_rules": []}},
        ),
    )

    assert decision.matched is False
    assert decision.reason in {"ambiguous hybrid match", "no hybrid auto-match"}


def test_decision_hard_gate_blocks_auto_match_even_with_high_scores() -> None:
    decision = HybridDecisionInput(
        confidence=0.99,
        lexical_score=0.95,
        attribute_score=0.90,
        reasons=["brand match", "model match"],
        blocked_reasons=["storage conflict against variant 123"],
        second_confidence=0.50,
    )

    assert has_critical_hard_gate(decision.blocked_reasons) is True
    assert should_auto_match_hybrid(decision) is False


def test_hybrid_debug_info_includes_conflicts_when_auto_match_is_blocked() -> None:
    conflicting_candidate = make_candidate(
        normalized_name="Samsung Galaxy S24 128GB",
        brand="Samsung",
        category="Phones",
        source_title="Samsung Galaxy S24 128GB",
        pack_count=None,
        weight=None,
        weight_unit=None,
    )
    service = HybridFallbackMatchingService(repository=FakeHybridMatchRepository([conflicting_candidate]))

    decision = service.match_normalized_record(
        db=None,
        normalized_record=make_normalized_record(
            normalized_name="Samsung Galaxy S24 256GB",
            source_title="Samsung Galaxy S24 256GB",
            brand="Samsung",
            source_brand="Samsung",
            category="Phones",
            pack_count=None,
            weight=None,
            weight_unit=None,
            source_attributes={"variant_parse": {"confidence": 0.0, "matched_rules": []}},
        ),
    )

    assert decision.debug is not None
    assert "storage conflict" in decision.debug.critical_conflict_flags
    assert decision.debug.final_decision_reason == "hybrid fallback found only conflicting or weak candidates"


def test_matching_service_runs_hybrid_after_exact_miss(caplog) -> None:
    hybrid_decision = MatchDecision(
        matched=False,
        reason="ambiguous hybrid match",
        candidate_product_variant_ids=["variant-1"],
    )
    service = MatchingService(
        exact_matcher=StubExactMatcher(MatchDecision(matched=False, reason="no exact match")),
        hybrid_matcher=StubHybridMatcher(hybrid_decision),
    )
    caplog.set_level("INFO", logger="app.matching.service")

    decision = service.match_normalized_record(db=None, normalized_record=make_normalized_record())

    assert decision.reason == hybrid_decision.reason
    assert decision.candidate_product_variant_ids == ["variant-1"]
    assert "matching_decision" in caplog.text
    assert "attempted_hybrid=True" in caplog.text
    assert "final_reason=ambiguous hybrid match" in caplog.text


def test_matching_service_preserves_exact_match_precedence(caplog) -> None:
    exact_decision = MatchDecision(
        matched=True,
        product_id="product-1",
        product_variant_id="variant-1",
        reason="exact match",
        match_strategy="exact",
    )
    service = MatchingService(
        exact_matcher=StubExactMatcher(exact_decision),
        hybrid_matcher=StubHybridMatcher(MatchDecision(matched=True, product_variant_id="variant-2")),
    )
    caplog.set_level("INFO", logger="app.matching.service")

    decision = service.match_normalized_record(db=None, normalized_record=make_normalized_record())

    assert decision.matched is True
    assert decision.match_strategy == "exact"
    assert decision.product_variant_id == "variant-1"
    assert "matching_decision" in caplog.text
    assert "attempted_hybrid=False" in caplog.text
    assert "final_strategy=exact" in caplog.text


def test_matching_service_keeps_exact_block_when_identifier_conflicts() -> None:
    exact_decision = MatchDecision(
        matched=False,
        reason="all exact matches blocked by critical variant conflict",
        blocked_reasons=["critical variant conflict for gtin"],
    )
    service = MatchingService(
        exact_matcher=StubExactMatcher(exact_decision),
        hybrid_matcher=StubHybridMatcher(MatchDecision(matched=True, product_variant_id="should-not-win")),
    )

    decision = service.match_normalized_record(db=None, normalized_record=make_normalized_record())

    assert decision.reason == exact_decision.reason
    assert decision.blocked_reasons == exact_decision.blocked_reasons
