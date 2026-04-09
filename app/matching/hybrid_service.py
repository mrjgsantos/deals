"""Hybrid fallback matcher.

This service gathers a small candidate set, scores it deterministically, and
delegates the final auto-match decision to the safety gates in decision.py.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.ingestion.variant_parser import VariantParseResult
from app.matching.decision import (
    HybridDecisionInput,
    MatchCandidateDebug,
    MatchDebugInfo,
    MatchDecision,
    has_critical_hard_gate,
    is_hybrid_ambiguous,
    should_auto_match_hybrid,
)
from app.matching.repository import HybridMatchCandidate, HybridMatchRepository, SQLAlchemyHybridMatchRepository
from app.matching.scoring import (
    CandidateFeatures,
    build_candidate_features,
    detect_hybrid_conflicts,
    score_hybrid_match,
)
from app.matching.variant_projection import (
    variant_result_from_candidate,
    variant_result_from_normalized_record,
)

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class RankedCandidate:
    candidate: HybridMatchCandidate
    features: CandidateFeatures
    confidence: float
    lexical_score: float
    lexical_overlap: int
    attribute_score: float
    reasons: list[str]


class HybridFallbackMatchingService:
    """Run the conservative second-pass matcher after an exact miss."""

    def __init__(self, repository: HybridMatchRepository | None = None) -> None:
        self.repository = repository or SQLAlchemyHybridMatchRepository()

    def match_normalized_record(self, db: Session, normalized_record) -> MatchDecision:
        incoming_features = build_candidate_features(
            normalized_record.source_title,
            brand=normalized_record.brand,
            variant=variant_result_from_normalized_record(normalized_record),
        )
        incoming_title_features = incoming_features.title_features
        retrieval_tokens = sorted(
            {
                token
                for token in incoming_title_features.normalized_title.split()
                if len(token) >= 3 and token not in {"the", "with", "for"}
            }
        )
        candidates = self.repository.find_candidates(
            db,
            brand=incoming_title_features.normalized_brand or self._clean_text(normalized_record.brand),
            title_tokens=retrieval_tokens,
        )
        if not candidates:
            return MatchDecision(
                matched=False,
                reason="no hybrid match",
                debug=MatchDebugInfo(
                    strategy="hybrid_fallback",
                    candidate_count_considered=0,
                    final_decision_reason="no hybrid match",
                ),
            )

        blocked_reasons: list[str] = []
        ranked_candidates: list[RankedCandidate] = []

        for candidate in candidates:
            candidate_features = build_candidate_features(
                candidate.source_title or candidate.normalized_name,
                brand=candidate.brand,
                variant=variant_result_from_candidate(
                    candidate,
                    normalized_text=(candidate.source_title or candidate.normalized_name).casefold(),
                ),
            )
            conflicts = detect_hybrid_conflicts(
                incoming_features,
                candidate_features,
                incoming_brand=normalized_record.brand,
                candidate_brand=candidate.brand,
            )
            if conflicts:
                blocked_reasons.extend(
                    [f"{reason} against variant {candidate.product_variant_id}" for reason in conflicts]
                )
                continue

            score = score_hybrid_match(
                incoming_features,
                candidate_features,
                incoming_brand=normalized_record.brand,
                candidate_brand=candidate.brand,
            )
            if score.lexical_overlap < 2 or score.lexical_score < 0.55:
                continue

            ranked_candidates.append(
                RankedCandidate(
                    candidate=candidate,
                    features=candidate_features,
                    confidence=score.confidence,
                    lexical_score=score.lexical_score,
                    lexical_overlap=score.lexical_overlap,
                    attribute_score=score.attribute_score,
                    reasons=score.reasons,
                )
            )

        if not ranked_candidates:
            decision = self._build_match_decision(
                matched=False,
                reason="hybrid fallback found only conflicting or weak candidates",
                ranked_candidates=ranked_candidates,
                candidate_count_considered=len(candidates),
                blocked_reasons=blocked_reasons,
            )
            self._log_debug(decision)
            return decision

        ranked_candidates.sort(
            key=lambda item: (
                -item.confidence,
                -item.lexical_score,
                -item.attribute_score,
                str(item.candidate.product_variant_id),
            )
        )
        top = ranked_candidates[0]
        second = ranked_candidates[1] if len(ranked_candidates) > 1 else None
        candidate_variant_ids = [str(item.candidate.product_variant_id) for item in ranked_candidates[:5]]
        candidate_product_ids = [str(item.candidate.product_id) for item in ranked_candidates[:5]]

        decision_input = HybridDecisionInput(
            confidence=top.confidence,
            lexical_score=top.lexical_score,
            attribute_score=top.attribute_score,
            reasons=top.reasons,
            blocked_reasons=blocked_reasons,
            second_confidence=second.confidence if second is not None else None,
        )

        if should_auto_match_hybrid(decision_input):
            decision = self._build_match_decision(
                matched=True,
                match_key="hybrid_fallback",
                match_value=top.candidate.normalized_name,
                reason="hybrid fallback auto-match",
                product_id=str(top.candidate.product_id),
                product_variant_id=str(top.candidate.product_variant_id),
                confidence=top.confidence,
                candidate_product_ids=candidate_product_ids,
                candidate_product_variant_ids=candidate_variant_ids,
                ranked_candidates=ranked_candidates,
                candidate_count_considered=len(candidates),
                blocked_reasons=blocked_reasons,
            )
            self._log_debug(decision)
            return decision

        if has_critical_hard_gate(blocked_reasons):
            decision = self._build_match_decision(
                matched=False,
                reason="hybrid hard gate blocked auto-match",
                confidence=top.confidence,
                candidate_product_ids=candidate_product_ids,
                candidate_product_variant_ids=candidate_variant_ids,
                ranked_candidates=ranked_candidates,
                candidate_count_considered=len(candidates),
                blocked_reasons=blocked_reasons,
            )
            self._log_debug(decision)
            return decision

        if is_hybrid_ambiguous(top.confidence, second.confidence if second is not None else None):
            decision = self._build_match_decision(
                matched=False,
                reason="ambiguous hybrid match",
                confidence=top.confidence,
                candidate_product_ids=candidate_product_ids,
                candidate_product_variant_ids=candidate_variant_ids,
                ranked_candidates=ranked_candidates,
                candidate_count_considered=len(candidates),
                blocked_reasons=blocked_reasons,
            )
            self._log_debug(decision)
            return decision

        decision = self._build_match_decision(
            matched=False,
            reason="no hybrid auto-match",
            confidence=top.confidence,
            candidate_product_ids=candidate_product_ids,
            candidate_product_variant_ids=candidate_variant_ids,
            ranked_candidates=ranked_candidates,
            candidate_count_considered=len(candidates),
            blocked_reasons=blocked_reasons,
        )
        self._log_debug(decision)
        return decision

    def _clean_text(self, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip().casefold()
        return cleaned or None

    def _build_match_decision(
        self,
        *,
        matched: bool,
        reason: str,
        ranked_candidates: list[RankedCandidate],
        candidate_count_considered: int,
        blocked_reasons: list[str],
        product_id: str | None = None,
        product_variant_id: str | None = None,
        match_key: str | None = None,
        match_value: str | None = None,
        confidence: float | None = None,
        candidate_product_ids: list[str] | None = None,
        candidate_product_variant_ids: list[str] | None = None,
    ) -> MatchDecision:
        return MatchDecision(
            matched=matched,
            product_id=product_id,
            product_variant_id=product_variant_id,
            match_key=match_key,
            match_value=match_value,
            reason=reason,
            blocked_reasons=blocked_reasons,
            match_strategy="hybrid_fallback",
            confidence=confidence,
            candidate_product_ids=candidate_product_ids or [],
            candidate_product_variant_ids=candidate_product_variant_ids or [],
            debug=self._build_debug_info(
                ranked_candidates=ranked_candidates,
                candidate_count_considered=candidate_count_considered,
                blocked_reasons=blocked_reasons,
                final_decision_reason=reason,
            ),
        )

    def _build_debug_info(
        self,
        *,
        ranked_candidates: list[RankedCandidate],
        candidate_count_considered: int,
        blocked_reasons: list[str],
        final_decision_reason: str,
    ) -> MatchDebugInfo:
        top = ranked_candidates[0] if ranked_candidates else None
        return MatchDebugInfo(
            strategy="hybrid_fallback",
            candidate_count_considered=candidate_count_considered,
            top_candidate_score=top.confidence if top is not None else None,
            top_candidate_lexical_score=top.lexical_score if top is not None else None,
            blocked_reasons=list(blocked_reasons),
            critical_conflict_flags=self._critical_conflict_flags(blocked_reasons),
            final_decision_reason=final_decision_reason,
            candidates=[
                MatchCandidateDebug(
                    product_id=str(item.candidate.product_id),
                    product_variant_id=str(item.candidate.product_variant_id),
                    confidence=item.confidence,
                    lexical_score=item.lexical_score,
                    attribute_score=item.attribute_score,
                    reasons=list(item.reasons),
                )
                for item in ranked_candidates[:5]
            ],
        )

    def _critical_conflict_flags(self, blocked_reasons: list[str]) -> list[str]:
        flags: list[str] = []
        for reason in blocked_reasons:
            normalized = reason.split(" against variant ", 1)[0]
            if normalized not in flags:
                flags.append(normalized)
        return flags

    def _log_debug(self, decision: MatchDecision) -> None:
        if decision.debug is None:
            return
        logger.info(
            "hybrid_match_decision strategy=%s matched=%s reason=%s candidate_count=%s top_score=%s top_lexical=%s critical_conflicts=%s",
            decision.debug.strategy,
            decision.matched,
            decision.debug.final_decision_reason,
            decision.debug.candidate_count_considered,
            decision.debug.top_candidate_score,
            decision.debug.top_candidate_lexical_score,
            decision.debug.critical_conflict_flags,
        )
