"""Primary matching entrypoints.

Exact matching stays first and highest-confidence; the hybrid fallback only runs
after an exact miss.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.ingestion.variant_parser import VariantParseResult, has_critical_variant_conflict
from app.matching.decision import MatchDecision
from app.matching.hybrid_service import HybridFallbackMatchingService
from app.matching.repository import ExactMatchCandidate, ExactMatchRepository, SQLAlchemyExactMatchRepository
from app.matching.variant_projection import (
    variant_result_from_candidate,
    variant_result_from_normalized_record,
)

logger = logging.getLogger(__name__)


class ExactMatchingService:
    """Resolve the strongest deterministic identifier match, if any."""

    def __init__(self, repository: ExactMatchRepository | None = None) -> None:
        self.repository = repository or SQLAlchemyExactMatchRepository()

    def match_normalized_record(self, db: Session, normalized_record) -> MatchDecision:
        incoming_variant = variant_result_from_normalized_record(normalized_record)
        source_attributes = normalized_record.source_attributes or {}

        gtin = self._first_non_empty(
            source_attributes.get("gtin"),
            source_attributes.get("ean"),
        )
        if gtin:
            decision = self._resolve_candidates(
                incoming_variant=incoming_variant,
                candidates=self.repository.find_by_gtin(db, gtin),
                match_key="gtin",
                match_value=gtin,
            )
            if decision.matched or decision.blocked_reasons:
                return decision

        asin = self._first_non_empty(source_attributes.get("asin"))
        if asin:
            decision = self._resolve_candidates(
                incoming_variant=incoming_variant,
                candidates=self.repository.find_by_asin(db, asin),
                match_key="asin",
                match_value=asin,
            )
            if decision.matched or decision.blocked_reasons:
                return decision

        mpn = self._first_non_empty(source_attributes.get("mpn"))
        brand = self._first_non_empty(normalized_record.brand)
        if mpn and brand:
            decision = self._resolve_candidates(
                incoming_variant=incoming_variant,
                candidates=self.repository.find_by_mpn_brand(db, mpn, brand),
                match_key="mpn_brand",
                match_value=f"{mpn}|{brand.casefold()}",
            )
            if decision.matched or decision.blocked_reasons:
                return decision

        return MatchDecision(matched=False, reason="no exact match")

    def _resolve_candidates(
        self,
        incoming_variant: VariantParseResult,
        candidates: list[ExactMatchCandidate],
        match_key: str,
        match_value: str,
    ) -> MatchDecision:
        if not candidates:
            return MatchDecision(matched=False, reason=f"no {match_key} match")

        eligible: list[ExactMatchCandidate] = []
        blocked_reasons: list[str] = []

        for candidate in candidates:
            candidate_variant = variant_result_from_candidate(candidate)
            if has_critical_variant_conflict(incoming_variant, candidate_variant):
                blocked_reasons.append(
                    f"critical variant conflict for {match_key}:{match_value} against variant {candidate.product_variant_id}"
                )
                continue
            eligible.append(candidate)

        distinct_variant_ids = {candidate.product_variant_id for candidate in eligible}
        if len(distinct_variant_ids) == 1:
            winner = eligible[0]
            return MatchDecision(
                matched=True,
                product_id=str(winner.product_id),
                product_variant_id=str(winner.product_variant_id),
                match_key=match_key,
                match_value=match_value,
                match_strategy="exact",
            )

        if len(distinct_variant_ids) > 1:
            blocked_reasons.append(f"ambiguous {match_key} match for {match_value}")
            return MatchDecision(
                matched=False,
                reason="ambiguous exact match",
                blocked_reasons=blocked_reasons,
            )

        return MatchDecision(
            matched=False,
            reason="all exact matches blocked by critical variant conflict",
            blocked_reasons=blocked_reasons,
        )

    def _first_non_empty(self, *values: str | None) -> str | None:
        for value in values:
            if value is None:
                continue
            stripped = str(value).strip()
            if stripped:
                return stripped
        return None


class MatchingService:
    """Run exact matching first, then the conservative hybrid fallback."""

    def __init__(
        self,
        exact_matcher: ExactMatchingService | None = None,
        hybrid_matcher: HybridFallbackMatchingService | None = None,
    ) -> None:
        self.exact_matcher = exact_matcher or ExactMatchingService()
        self.hybrid_matcher = hybrid_matcher or HybridFallbackMatchingService()

    def match_normalized_record(self, db: Session, normalized_record) -> MatchDecision:
        exact_decision = self.exact_matcher.match_normalized_record(db, normalized_record)
        if exact_decision.matched or exact_decision.blocked_reasons:
            self._log_decision(
                normalized_record,
                exact_decision=exact_decision,
                final_decision=exact_decision,
                attempted_hybrid=False,
            )
            return exact_decision

        hybrid_decision = self.hybrid_matcher.match_normalized_record(db, normalized_record)
        if (
            hybrid_decision.matched
            or hybrid_decision.blocked_reasons
            or hybrid_decision.candidate_product_variant_ids
            or hybrid_decision.reason != "no hybrid match"
        ):
            self._log_decision(
                normalized_record,
                exact_decision=exact_decision,
                final_decision=hybrid_decision,
                attempted_hybrid=True,
            )
            return hybrid_decision

        self._log_decision(
            normalized_record,
            exact_decision=exact_decision,
            final_decision=exact_decision,
            attempted_hybrid=True,
        )
        return exact_decision

    def _log_decision(
        self,
        normalized_record,
        *,
        exact_decision: MatchDecision,
        final_decision: MatchDecision,
        attempted_hybrid: bool,
    ) -> None:
        debug = final_decision.debug
        final_strategy = final_decision.match_strategy or ("hybrid_fallback" if attempted_hybrid else "exact")
        logger.info(
            "matching_decision external_id=%s attempted_hybrid=%s exact_reason=%s final_strategy=%s matched=%s final_reason=%s match_key=%s match_value=%s blocked_reason_count=%s candidate_count=%s confidence=%s",
            normalized_record.external_id,
            attempted_hybrid,
            exact_decision.reason,
            final_strategy,
            final_decision.matched,
            final_decision.reason,
            final_decision.match_key,
            final_decision.match_value,
            len(final_decision.blocked_reasons or []),
            debug.candidate_count_considered if debug is not None else len(final_decision.candidate_product_variant_ids or []),
            final_decision.confidence,
        )
