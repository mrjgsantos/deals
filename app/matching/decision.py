"""Decision models and safety gates for matching."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from sqlalchemy.orm import Session


@dataclass(slots=True)
class MatchDecision:
    matched: bool
    product_id: str | None = None
    product_variant_id: str | None = None
    match_key: str | None = None
    match_value: str | None = None
    reason: str | None = None
    blocked_reasons: list[str] = field(default_factory=list)
    match_strategy: str | None = None
    confidence: float | None = None
    candidate_product_ids: list[str] = field(default_factory=list)
    candidate_product_variant_ids: list[str] = field(default_factory=list)
    debug: "MatchDebugInfo | None" = None


class Matcher(Protocol):
    def match_normalized_record(self, db: Session, normalized_record) -> MatchDecision:
        ...


AUTO_MATCH_CONFIDENCE = 0.82
AUTO_MATCH_LEXICAL_SCORE = 0.75
AUTO_MATCH_ATTRIBUTE_SCORE = 0.60
AMBIGUITY_MARGIN = 0.10
CRITICAL_HARD_GATES = {
    "brand conflict",
    "storage conflict",
    "pack_count conflict",
    "model conflict",
    "generation conflict",
}


@dataclass(slots=True)
class HybridDecisionInput:
    confidence: float
    lexical_score: float
    attribute_score: float
    reasons: list[str] = field(default_factory=list)
    blocked_reasons: list[str] = field(default_factory=list)
    second_confidence: float | None = None


@dataclass(slots=True)
class MatchCandidateDebug:
    product_id: str
    product_variant_id: str
    confidence: float
    lexical_score: float
    attribute_score: float
    reasons: list[str] = field(default_factory=list)


@dataclass(slots=True)
class MatchDebugInfo:
    strategy: str
    candidate_count_considered: int = 0
    top_candidate_score: float | None = None
    top_candidate_lexical_score: float | None = None
    blocked_reasons: list[str] = field(default_factory=list)
    critical_conflict_flags: list[str] = field(default_factory=list)
    final_decision_reason: str | None = None
    candidates: list[MatchCandidateDebug] = field(default_factory=list)


def should_auto_match_hybrid(decision: HybridDecisionInput) -> bool:
    """Return True only when the hybrid result clears all safety gates."""
    if has_critical_hard_gate(decision.blocked_reasons):
        return False
    if decision.confidence < AUTO_MATCH_CONFIDENCE:
        return False
    if decision.lexical_score < AUTO_MATCH_LEXICAL_SCORE:
        return False
    if decision.attribute_score < AUTO_MATCH_ATTRIBUTE_SCORE:
        return False
    if "brand match" not in decision.reasons:
        return False
    if "model match" not in decision.reasons:
        return False
    if decision.second_confidence is not None and abs(decision.confidence - decision.second_confidence) <= AMBIGUITY_MARGIN:
        return False
    return True


def is_hybrid_ambiguous(top_confidence: float, second_confidence: float | None) -> bool:
    """Treat near-tied candidates as ambiguous to prefer false negatives."""
    if second_confidence is None:
        return False
    return abs(top_confidence - second_confidence) <= AMBIGUITY_MARGIN


def has_critical_hard_gate(blocked_reasons: list[str]) -> bool:
    return any(_normalize_block_reason(reason) in CRITICAL_HARD_GATES for reason in blocked_reasons)


def _normalize_block_reason(reason: str) -> str:
    return reason.split(" against variant ", 1)[0].strip().casefold()
