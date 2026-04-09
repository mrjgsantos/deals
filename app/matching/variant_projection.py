"""Helpers that project records and candidates into comparable variant views."""

from __future__ import annotations

from app.ingestion.variant_parser import VariantAttributes, VariantParseResult


def variant_result_from_normalized_record(normalized_record) -> VariantParseResult:
    """Build a comparable variant representation from a normalized ingest record."""
    variant_parse = (normalized_record.source_attributes or {}).get("variant_parse") or {}
    return VariantParseResult(
        normalized_text=normalized_record.source_title.casefold(),
        attributes=VariantAttributes(
            pack_count=normalized_record.pack_count,
            quantity=normalized_record.quantity,
            quantity_unit=normalized_record.quantity_unit,
            weight=normalized_record.weight,
            weight_unit=normalized_record.weight_unit,
            volume=normalized_record.volume,
            volume_unit=normalized_record.volume_unit,
            size=normalized_record.size,
            color=normalized_record.color,
            material=normalized_record.material,
            is_bundle=normalized_record.is_bundle,
        ),
        confidence=float(variant_parse.get("confidence", 0.0)),
        matched_rules=list(variant_parse.get("matched_rules", [])),
    )


def variant_result_from_candidate(candidate, *, normalized_text: str = "") -> VariantParseResult:
    """Build a comparable variant representation from an exact or hybrid candidate."""
    return VariantParseResult(
        normalized_text=normalized_text,
        attributes=VariantAttributes(
            pack_count=candidate.pack_count,
            quantity=candidate.quantity,
            quantity_unit=candidate.quantity_unit,
            weight=candidate.weight,
            weight_unit=candidate.weight_unit,
            volume=candidate.volume,
            volume_unit=candidate.volume_unit,
            size=candidate.size,
            color=candidate.color,
            material=candidate.material,
            is_bundle=candidate.is_bundle,
        ),
        confidence=1.0,
        matched_rules=[],
    )
