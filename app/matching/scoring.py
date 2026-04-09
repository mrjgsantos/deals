"""Deterministic scoring inputs for the hybrid matcher."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.ingestion.variant_parser import VariantAttributes, VariantParseResult, detect_variant_conflicts
from app.matching.feature_extraction import TitleNormalizationFeatures, extract_title_normalization_features


GENERATION_PATTERNS = (
    re.compile(r"\b(?:gen|generation)\s*(\d+)\b"),
    re.compile(r"\b(\d+)(?:st|nd|rd|th)\s+gen\b"),
    re.compile(r"\b(\d+)\s+(?:st|nd|rd|th)\s+gen\b"),
)
TOKEN_RE = re.compile(r"[a-z0-9]+")
STOPWORDS = {"the", "with", "for", "and", "by", "of"}


@dataclass(slots=True)
class CandidateFeatures:
    title_features: TitleNormalizationFeatures
    variant: VariantParseResult


@dataclass(slots=True)
class HybridScoreBreakdown:
    lexical_score: float
    lexical_overlap: int
    attribute_score: float
    confidence: float
    reasons: list[str]


def build_candidate_features(title: str, *, brand: str | None, variant: VariantParseResult) -> CandidateFeatures:
    """Normalize title-derived signals once so scoring stays consistent."""
    return CandidateFeatures(
        title_features=extract_title_normalization_features(title, brand=brand),
        variant=variant,
    )


def score_hybrid_match(
    incoming: CandidateFeatures,
    candidate: CandidateFeatures,
    *,
    incoming_brand: str | None,
    candidate_brand: str | None,
) -> HybridScoreBreakdown:
    """Score a candidate without making the final match decision."""
    reasons: list[str] = []

    lexical_score, lexical_overlap = lexical_similarity(
        incoming.title_features,
        candidate.title_features,
    )
    if lexical_overlap < 2 or lexical_score < 0.55:
        reasons.append("weak lexical similarity")

    feature_weights = [
        (0.30, _same_text(incoming.title_features.normalized_brand or _normalize_text(incoming_brand), candidate.title_features.normalized_brand or _normalize_text(candidate_brand)), "brand match"),
        (0.25, _same_text(incoming.title_features.normalized_model, candidate.title_features.normalized_model), "model match"),
        (0.20, _same_text(incoming.title_features.normalized_storage, candidate.title_features.normalized_storage), "storage match"),
        (0.10, _same_text(incoming.title_features.normalized_color, candidate.title_features.normalized_color), "color match"),
        (0.15, _same_value(incoming.title_features.normalized_pack_count, candidate.title_features.normalized_pack_count), "pack_count match"),
    ]

    matched_weight = 0.0
    possible_weight = 0.0
    for weight, is_match, label in feature_weights:
        if is_match is None:
            continue
        possible_weight += weight
        if is_match:
            matched_weight += weight
            reasons.append(label)

    attribute_score = round((matched_weight / possible_weight), 2) if possible_weight else 0.0

    variant_score = structured_variant_similarity(incoming.variant, candidate.variant)
    confidence = round((0.45 * lexical_score) + (0.45 * attribute_score) + (0.10 * variant_score), 2)
    return HybridScoreBreakdown(
        lexical_score=lexical_score,
        lexical_overlap=lexical_overlap,
        attribute_score=attribute_score,
        confidence=confidence,
        reasons=reasons,
    )


def detect_hybrid_conflicts(
    incoming: CandidateFeatures,
    candidate: CandidateFeatures,
    *,
    incoming_brand: str | None,
    candidate_brand: str | None,
) -> list[str]:
    """Return only explicit conflicts; missing weak signals are ignored."""
    conflicts: list[str] = []

    normalized_incoming_brand = incoming.title_features.normalized_brand or _normalize_text(incoming_brand)
    normalized_candidate_brand = candidate.title_features.normalized_brand or _normalize_text(candidate_brand)
    if normalized_incoming_brand and normalized_candidate_brand and normalized_incoming_brand != normalized_candidate_brand:
        conflicts.append("brand conflict")

    incoming_storage = incoming.title_features.normalized_storage
    candidate_storage = candidate.title_features.normalized_storage
    if incoming_storage and candidate_storage and incoming_storage != candidate_storage:
        conflicts.append("storage conflict")

    incoming_pack = incoming.title_features.normalized_pack_count
    candidate_pack = candidate.title_features.normalized_pack_count
    if incoming_pack is not None and candidate_pack is not None and incoming_pack != candidate_pack:
        conflicts.append("pack_count conflict")

    incoming_model = incoming.title_features.normalized_model
    candidate_model = candidate.title_features.normalized_model
    if incoming_model and candidate_model and incoming_model != candidate_model:
        conflicts.append("model conflict")

    incoming_generation = _extract_generation_signal(incoming.title_features.normalized_title)
    candidate_generation = _extract_generation_signal(candidate.title_features.normalized_title)
    if incoming_generation and candidate_generation and incoming_generation != candidate_generation:
        conflicts.append("generation conflict")

    for conflict in detect_variant_conflicts(incoming.variant, candidate.variant):
        if conflict.critical:
            conflicts.append(f"{conflict.field} conflict")

    return conflicts


def lexical_similarity(
    left_features: TitleNormalizationFeatures,
    right_features: TitleNormalizationFeatures,
) -> tuple[float, int]:
    left_tokens = _lexical_tokens(left_features)
    right_tokens = _lexical_tokens(right_features)
    if not left_tokens or not right_tokens:
        return 0.0, 0
    overlap = len(left_tokens & right_tokens)
    if overlap == 0:
        return 0.0, 0
    return round((2 * overlap) / (len(left_tokens) + len(right_tokens)), 2), overlap


def structured_variant_similarity(left: VariantParseResult, right: VariantParseResult) -> float:
    weighted_checks = [
        (0.25, left.attributes.pack_count, right.attributes.pack_count),
        (0.25, _measure_pair(left.attributes.quantity, left.attributes.quantity_unit), _measure_pair(right.attributes.quantity, right.attributes.quantity_unit)),
        (0.25, _measure_pair(left.attributes.weight, left.attributes.weight_unit), _measure_pair(right.attributes.weight, right.attributes.weight_unit)),
        (0.15, _measure_pair(left.attributes.volume, left.attributes.volume_unit), _measure_pair(right.attributes.volume, right.attributes.volume_unit)),
        (0.10, left.attributes.size, right.attributes.size),
    ]
    possible = 0.0
    matched = 0.0
    for weight, left_value, right_value in weighted_checks:
        if left_value is None or right_value is None:
            continue
        possible += weight
        if left_value == right_value:
            matched += weight
    return round((matched / possible), 2) if possible else 0.0


def _extract_generation_signal(title: str) -> str | None:
    for pattern in GENERATION_PATTERNS:
        match = pattern.search(title)
        if match:
            return next((group for group in match.groups() if group), None)
    return None


def _normalize_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip().casefold()
    return cleaned or None


def _normalized_tokens(title: str) -> set[str]:
    return {token for token in TOKEN_RE.findall(title.casefold()) if len(token) >= 2 and token not in STOPWORDS}


def _lexical_tokens(features: TitleNormalizationFeatures) -> set[str]:
    tokens = _normalized_tokens(features.normalized_title)
    if features.normalized_storage:
        storage_parts = set(TOKEN_RE.findall(features.normalized_storage))
        tokens.difference_update(storage_parts)
        tokens.add(features.normalized_storage)
    if features.normalized_model:
        tokens.update(token for token in features.normalized_model.split("-") if token)
    return tokens


def _measure_pair(value, unit):
    if value is None:
        return None
    return f"{value}:{unit or ''}"


def _same_text(left: str | None, right: str | None) -> bool | None:
    if left is None or right is None:
        return None
    return left == right


def _same_value(left, right) -> bool | None:
    if left is None or right is None:
        return None
    return left == right
