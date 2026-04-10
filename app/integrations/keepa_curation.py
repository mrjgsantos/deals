from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any, Iterable

from app.ingestion.amazon_identifiers import extract_amazon_asin_from_url, normalize_asin
from app.integrations.keepa_payloads import (
    keepa_product_ingest_rejection_reason,
    normalize_keepa_payload_for_ingest,
    normalize_keepa_product_for_ingest,
)

TOKEN_SPLIT_PATTERN = re.compile(r"[\s,;]+")


@dataclass(slots=True)
class AsinInputIssue:
    raw_value: str
    source: str
    outcome: str
    reason: str
    normalized_asin: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "raw_value": self.raw_value,
            "source": self.source,
            "outcome": self.outcome,
            "reason": self.reason,
            "normalized_asin": self.normalized_asin,
        }


@dataclass(slots=True)
class CuratedAsinInputs:
    selected_source: str
    raw_candidates: list[str]
    accepted_asins: list[str]
    issues: list[AsinInputIssue]

    @property
    def counts_by_outcome(self) -> dict[str, int]:
        counts = Counter(issue.outcome for issue in self.issues)
        return dict(sorted(counts.items()))

    @property
    def counts_by_reason(self) -> dict[str, int]:
        counts = Counter(issue.reason for issue in self.issues)
        return dict(sorted(counts.items()))


@dataclass(slots=True)
class KeepaBatchOutcome:
    outcome: str
    reason: str
    requested_asin: str | None = None
    returned_asin: str | None = None
    domain_id: int | None = None
    title: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "requested_asin": self.requested_asin,
            "returned_asin": self.returned_asin,
            "outcome": self.outcome,
            "reason": self.reason,
            "domain_id": self.domain_id,
            "title": self.title,
        }


@dataclass(slots=True)
class KeepaBatchPreflightResult:
    payload: dict[str, Any]
    fetched_products: int
    outcomes: list[KeepaBatchOutcome]

    @property
    def counts_by_outcome(self) -> dict[str, int]:
        counts = Counter(outcome.outcome for outcome in self.outcomes)
        return dict(sorted(counts.items()))

    @property
    def skipped_outcomes(self) -> list[KeepaBatchOutcome]:
        return [
            outcome
            for outcome in self.outcomes
            if outcome.outcome != "valid_and_enrichable"
        ]


def extract_asin_candidates_from_text(raw_text: str) -> list[str]:
    raw = raw_text.strip()
    if not raw:
        return []

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return _split_candidate_tokens(raw)

    if isinstance(payload, list):
        return _split_candidate_tokens(" ".join(str(item) for item in payload))

    raise ValueError("ASIN file must contain a JSON array or raw text with ASINs / Amazon URLs.")


def expand_raw_asin_candidates(values: Iterable[object]) -> list[str]:
    candidates: list[str] = []
    for value in values:
        raw = str(value).strip()
        if not raw:
            continue
        candidates.extend(_split_candidate_tokens(raw))
    return candidates


def curate_asin_candidates(values: Iterable[object], *, source: str) -> CuratedAsinInputs:
    raw_candidates = expand_raw_asin_candidates(values)
    accepted_asins: list[str] = []
    issues: list[AsinInputIssue] = []
    seen: set[str] = set()

    for raw_value in raw_candidates:
        normalized = normalize_asin(raw_value)
        if normalized is None:
            normalized = extract_amazon_asin_from_url(raw_value)

        if normalized is None:
            issues.append(
                AsinInputIssue(
                    raw_value=raw_value,
                    source=source,
                    outcome="invalid_requested_input",
                    reason="invalid_asin_or_amazon_url",
                )
            )
            continue

        if normalized in seen:
            issues.append(
                AsinInputIssue(
                    raw_value=raw_value,
                    source=source,
                    outcome="duplicate_requested_input",
                    reason="duplicate_asin",
                    normalized_asin=normalized,
                )
            )
            continue

        seen.add(normalized)
        accepted_asins.append(normalized)

    return CuratedAsinInputs(
        selected_source=source,
        raw_candidates=raw_candidates,
        accepted_asins=accepted_asins,
        issues=issues,
    )


def preflight_keepa_batch_for_bulk_ingest(
    payload: dict[str, Any],
    *,
    requested_asins: list[str],
    domain_id: int,
) -> KeepaBatchPreflightResult:
    normalized_payload = normalize_keepa_payload_for_ingest(payload, domain_id=domain_id)
    raw_products = payload.get("products")
    if not isinstance(raw_products, list):
        raw_products = []

    requested_set = set(requested_asins)
    entries_by_asin: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = {}
    outcomes: list[KeepaBatchOutcome] = []

    fetched_products = 0

    for raw_product in raw_products:
        if not isinstance(raw_product, dict):
            continue
        fetched_products += 1
        normalized_product = normalize_keepa_product_for_ingest(raw_product, default_domain_id=domain_id)
        returned_asin = normalize_asin(raw_product.get("asin")) or normalize_asin(normalized_product.get("asin"))
        explicit_domain_id = _coerce_int(raw_product.get("domainId"))
        resolved_domain_id = explicit_domain_id or _coerce_int(normalized_product.get("domainId"))
        title = str(normalized_product.get("title") or "").strip() or None

        if returned_asin is None:
            outcomes.append(
                KeepaBatchOutcome(
                    outcome="invalid_keepa_payload_product",
                    reason="missing_or_invalid_asin",
                    domain_id=resolved_domain_id,
                    title=title,
                )
            )
            continue

        entries_by_asin.setdefault(returned_asin, []).append((raw_product, normalized_product))

    accepted_products: list[dict[str, Any]] = []

    for requested_asin in requested_asins:
        entries = entries_by_asin.get(requested_asin, [])
        if not entries:
            outcomes.append(
                KeepaBatchOutcome(
                    requested_asin=requested_asin,
                    outcome="not_found",
                    reason="requested_asin_not_returned",
                )
            )
            continue

        raw_product, normalized_product = entries[0]
        explicit_domain_id = _coerce_int(raw_product.get("domainId"))
        resolved_domain_id = explicit_domain_id or _coerce_int(normalized_product.get("domainId"))
        title = str(normalized_product.get("title") or "").strip() or None

        if len(entries) > 1:
            for duplicate_raw_product, duplicate_normalized_product in entries[1:]:
                outcomes.append(
                    KeepaBatchOutcome(
                        requested_asin=requested_asin,
                        returned_asin=requested_asin,
                        outcome="duplicate_payload_product",
                        reason="keepa_returned_duplicate_asin",
                        domain_id=_coerce_int(duplicate_raw_product.get("domainId"))
                        or _coerce_int(duplicate_normalized_product.get("domainId")),
                        title=str(duplicate_normalized_product.get("title") or "").strip() or None,
                    )
                )

        if explicit_domain_id is not None and explicit_domain_id != domain_id:
            outcomes.append(
                KeepaBatchOutcome(
                    requested_asin=requested_asin,
                    returned_asin=requested_asin,
                    outcome="wrong_marketplace",
                    reason=f"requested_domain_{domain_id}_returned_domain_{explicit_domain_id}",
                    domain_id=explicit_domain_id,
                    title=title,
                )
            )
            continue

        rejection_reason = keepa_product_ingest_rejection_reason(normalized_product)
        if rejection_reason is not None:
            outcomes.append(
                KeepaBatchOutcome(
                    requested_asin=requested_asin,
                    returned_asin=requested_asin,
                    outcome="valid_but_incomplete",
                    reason=rejection_reason,
                    domain_id=resolved_domain_id,
                    title=title,
                )
            )
            continue

        accepted_products.append(normalized_product)
        outcomes.append(
            KeepaBatchOutcome(
                requested_asin=requested_asin,
                returned_asin=requested_asin,
                outcome="valid_and_enrichable",
                reason="ready_for_ingest",
                domain_id=resolved_domain_id,
                title=title,
            )
        )

    for returned_asin, entries in entries_by_asin.items():
        if returned_asin in requested_set:
            continue
        for raw_product, normalized_product in entries:
            outcomes.append(
                KeepaBatchOutcome(
                    returned_asin=returned_asin,
                    outcome="unexpected_payload_product",
                    reason="returned_asin_not_requested",
                    domain_id=_coerce_int(raw_product.get("domainId"))
                    or _coerce_int(normalized_product.get("domainId")),
                    title=str(normalized_product.get("title") or "").strip() or None,
                )
            )

    filtered_payload = dict(normalized_payload)
    filtered_payload["products"] = accepted_products

    return KeepaBatchPreflightResult(
        payload=filtered_payload,
        fetched_products=fetched_products,
        outcomes=outcomes,
    )


def _split_candidate_tokens(raw_text: str) -> list[str]:
    candidates: list[str] = []
    for line in raw_text.splitlines():
        without_comment = line.split("#", 1)[0].strip()
        if not without_comment:
            continue
        candidates.extend(token for token in TOKEN_SPLIT_PATTERN.split(without_comment) if token)
    return candidates


def _coerce_int(value: object) -> int | None:
    try:
        if value is not None:
            return int(value)
    except (TypeError, ValueError):
        return None
    return None
