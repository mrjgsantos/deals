from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal

from app.ingestion.variant_helpers import (
    canonical_unit,
    compact_decimal,
    confidence_score,
    decimal_from_match,
    normalize_variant_text,
    slug_token,
)


PACK_X_WEIGHT_RE = re.compile(
    r"(?P<count>\d+)\s*x\s*(?P<amount>\d+(?:\.\d+)?)\s*(?P<unit>kg|g|lb|lbs|oz|l|lt|ltr|ml|cl)\b"
)
PACK_ONLY_RE = re.compile(
    r"(?:(?P<prefix>\d+)\s*(?:pack|pk)\b|(?P<dash>\d+)-pack\b|pack of\s*(?P<of>\d+)\b|set of\s*(?P<set>\d+)\b)"
)
SINGLE_RE = re.compile(r"\b(single unit|single|standalone)\b")
WEIGHT_RE = re.compile(r"(?P<amount>\d+(?:\.\d+)?)\s*(?P<unit>kg|g|lb|lbs|oz)\b")
VOLUME_RE = re.compile(r"(?P<amount>\d+(?:\.\d+)?)\s*(?P<unit>ml|l|lt|ltr|cl)\b")
SIZE_DIMENSION_RE = re.compile(r"\b(?P<size>\d+(?:\.\d+)?)\s*(?P<unit>cm|mm|in|inch|inches)\b")
SIZE_LABEL_RE = re.compile(r"\bsize\s*(?P<size>[a-z0-9.\-]+)\b")
QUANTITY_RE = re.compile(
    r"\b(?P<amount>\d+(?:\.\d+)?)\s*(?P<unit>count|ct|pcs|pc|pieces|piece|capsules|capsule|tablets|tablet|pods|pod|bags|bag|units|unit)\b"
)
COLOR_RE = re.compile(
    r"\b(black|white|red|blue|green|yellow|silver|gold|gray|grey|pink|orange|purple|brown|beige|ivory|navy)\b"
)
MATERIAL_RE = re.compile(
    r"\b(stainless steel|cast iron|silicone|ceramic|cotton|leather|plastic|wood|glass|aluminum|aluminium|jute)\b"
)
BUNDLE_RE = re.compile(
    r"\b(bundle|kit|starter kit|gift set|set with|bundle with|with accessory|with accessories|with case|with charger)\b"
)


CRITICAL_ATTRIBUTE_FIELDS = {
    "pack_count",
    "quantity",
    "quantity_unit",
    "weight",
    "weight_unit",
    "volume",
    "volume_unit",
    "size",
    "is_bundle",
}


@dataclass(slots=True)
class VariantAttributes:
    pack_count: int | None = None
    quantity: Decimal | None = None
    quantity_unit: str | None = None
    weight: Decimal | None = None
    weight_unit: str | None = None
    volume: Decimal | None = None
    volume_unit: str | None = None
    size: str | None = None
    color: str | None = None
    material: str | None = None
    is_bundle: bool = False


@dataclass(slots=True)
class VariantParseResult:
    normalized_text: str
    attributes: VariantAttributes
    confidence: float
    matched_rules: list[str] = field(default_factory=list)

    def variant_key(self) -> str:
        parts = []
        if self.attributes.pack_count is not None:
            parts.append(f"pack:{self.attributes.pack_count}")
        if self.attributes.quantity is not None:
            parts.append(
                f"qty:{compact_decimal(self.attributes.quantity)}:{self.attributes.quantity_unit or ''}"
            )
        if self.attributes.weight is not None:
            parts.append(
                f"weight:{compact_decimal(self.attributes.weight)}:{self.attributes.weight_unit or ''}"
            )
        if self.attributes.volume is not None:
            parts.append(
                f"volume:{compact_decimal(self.attributes.volume)}:{self.attributes.volume_unit or ''}"
            )
        if self.attributes.size is not None:
            parts.append(f"size:{self.attributes.size}")
        if self.attributes.color is not None:
            parts.append(f"color:{self.attributes.color}")
        if self.attributes.material is not None:
            parts.append(f"material:{self.attributes.material}")
        parts.append(f"bundle:{str(self.attributes.is_bundle).lower()}")
        return "|".join(parts)

    def as_dict(self) -> dict[str, object]:
        return {
            "pack_count": self.attributes.pack_count,
            "quantity": compact_decimal(self.attributes.quantity),
            "quantity_unit": self.attributes.quantity_unit,
            "weight": compact_decimal(self.attributes.weight),
            "weight_unit": self.attributes.weight_unit,
            "volume": compact_decimal(self.attributes.volume),
            "volume_unit": self.attributes.volume_unit,
            "size": self.attributes.size,
            "color": self.attributes.color,
            "material": self.attributes.material,
            "is_bundle": self.attributes.is_bundle,
            "confidence": self.confidence,
            "matched_rules": self.matched_rules,
            "variant_key": self.variant_key(),
        }


@dataclass(slots=True)
class VariantConflict:
    field: str
    left: object
    right: object
    critical: bool
    reason: str


def parse_variant_attributes(title: str) -> VariantParseResult:
    normalized_text = normalize_variant_text(title)
    attributes = VariantAttributes()
    matched_rules: list[str] = []

    pack_x_weight_match = PACK_X_WEIGHT_RE.search(normalized_text)
    if pack_x_weight_match:
        attributes.pack_count = int(pack_x_weight_match.group("count"))
        amount = decimal_from_match(pack_x_weight_match.group("amount"))
        unit = canonical_unit(pack_x_weight_match.group("unit"))
        if unit in {"kg", "g", "lb", "oz"}:
            attributes.weight = amount
            attributes.weight_unit = unit
        elif unit in {"ml", "l", "cl"}:
            attributes.volume = amount
            attributes.volume_unit = unit
        matched_rules.append("pack_x_measure")
    else:
        pack_only_match = PACK_ONLY_RE.search(normalized_text)
        if pack_only_match:
            pack_value = (
                pack_only_match.group("prefix")
                or pack_only_match.group("dash")
                or pack_only_match.group("of")
                or pack_only_match.group("set")
            )
            attributes.pack_count = int(pack_value)
            matched_rules.append("pack_count")
        elif SINGLE_RE.search(normalized_text):
            attributes.pack_count = 1
            matched_rules.append("single_unit")

        weight_match = WEIGHT_RE.search(normalized_text)
        if weight_match:
            attributes.weight = decimal_from_match(weight_match.group("amount"))
            attributes.weight_unit = canonical_unit(weight_match.group("unit"))
            matched_rules.append("weight")

        volume_match = VOLUME_RE.search(normalized_text)
        if volume_match:
            attributes.volume = decimal_from_match(volume_match.group("amount"))
            attributes.volume_unit = canonical_unit(volume_match.group("unit"))
            matched_rules.append("volume")

    quantity_match = QUANTITY_RE.search(normalized_text)
    if quantity_match:
        quantity_unit = canonical_unit(quantity_match.group("unit"))
        if quantity_unit not in {"cm", "mm", "in"}:
            attributes.quantity = decimal_from_match(quantity_match.group("amount"))
            attributes.quantity_unit = quantity_unit
            matched_rules.append("quantity")

    size_dimension_match = SIZE_DIMENSION_RE.search(normalized_text)
    if size_dimension_match:
        amount = decimal_from_match(size_dimension_match.group("size"))
        unit = canonical_unit(size_dimension_match.group("unit"))
        attributes.size = f"{compact_decimal(amount)}{unit}"
        matched_rules.append("size_dimension")
    else:
        size_label_match = SIZE_LABEL_RE.search(normalized_text)
        if size_label_match:
            attributes.size = slug_token(size_label_match.group("size"))
            matched_rules.append("size_label")

    color_match = COLOR_RE.search(normalized_text)
    if color_match:
        attributes.color = slug_token(color_match.group(1))
        matched_rules.append("color")

    material_match = MATERIAL_RE.search(normalized_text)
    if material_match:
        attributes.material = slug_token(material_match.group(1))
        matched_rules.append("material")

    if BUNDLE_RE.search(normalized_text):
        attributes.is_bundle = True
        matched_rules.append("bundle")

    return VariantParseResult(
        normalized_text=normalized_text,
        attributes=attributes,
        confidence=confidence_score(len(matched_rules), 6),
        matched_rules=matched_rules,
    )


def detect_variant_conflicts(left: VariantParseResult, right: VariantParseResult) -> list[VariantConflict]:
    conflicts: list[VariantConflict] = []
    if left.attributes.pack_count != right.attributes.pack_count:
        explicit_pack_count = left.attributes.pack_count if left.attributes.pack_count is not None else right.attributes.pack_count
        if explicit_pack_count is not None and explicit_pack_count > 1:
            conflicts.append(
                VariantConflict(
                    field="pack_count",
                    left=left.attributes.pack_count,
                    right=right.attributes.pack_count,
                    critical=True,
                    reason="pack_count differs",
                )
            )

    comparisons = [
        ("pack_count", left.attributes.pack_count, right.attributes.pack_count),
        ("quantity", compact_decimal(left.attributes.quantity), compact_decimal(right.attributes.quantity)),
        ("quantity_unit", left.attributes.quantity_unit, right.attributes.quantity_unit),
        ("weight", compact_decimal(left.attributes.weight), compact_decimal(right.attributes.weight)),
        ("weight_unit", left.attributes.weight_unit, right.attributes.weight_unit),
        ("volume", compact_decimal(left.attributes.volume), compact_decimal(right.attributes.volume)),
        ("volume_unit", left.attributes.volume_unit, right.attributes.volume_unit),
        ("size", left.attributes.size, right.attributes.size),
        ("color", left.attributes.color, right.attributes.color),
        ("material", left.attributes.material, right.attributes.material),
        ("is_bundle", left.attributes.is_bundle, right.attributes.is_bundle),
    ]

    for field, left_value, right_value in comparisons:
        if left_value is None or right_value is None:
            continue
        if left_value == right_value:
            continue
        if field == "pack_count":
            continue
        conflicts.append(
            VariantConflict(
                field=field,
                left=left_value,
                right=right_value,
                critical=field in CRITICAL_ATTRIBUTE_FIELDS,
                reason=f"{field} differs",
            )
        )
    return conflicts


def has_critical_variant_conflict(left: VariantParseResult, right: VariantParseResult) -> bool:
    return any(conflict.critical for conflict in detect_variant_conflicts(left, right))
