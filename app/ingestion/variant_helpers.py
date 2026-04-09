from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation


WHITESPACE_RE = re.compile(r"\s+")
TOKEN_SPLIT_RE = re.compile(r"[^a-z0-9]+")


def normalize_variant_text(value: str) -> str:
    normalized = value.casefold()
    normalized = normalized.replace("×", "x")
    normalized = normalized.replace("‑", "-")
    normalized = normalized.replace("–", "-")
    normalized = normalized.replace("—", "-")
    normalized = normalized.replace("_", " ")
    normalized = re.sub(r"(?<=\d)(?=[a-z])", " ", normalized)
    normalized = re.sub(r"(?<=[a-z])(?=\d)", " ", normalized)
    normalized = WHITESPACE_RE.sub(" ", normalized).strip()
    return normalized


def slug_token(value: str) -> str:
    return "-".join(token for token in TOKEN_SPLIT_RE.split(value.casefold()) if token)


def decimal_from_match(value: str | None) -> Decimal | None:
    if not value:
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def compact_decimal(value: Decimal | None) -> str | None:
    if value is None:
        return None
    normalized = value.normalize()
    text = format(normalized, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def canonical_unit(unit: str | None) -> str | None:
    if unit is None:
        return None

    mapping = {
        "kg": "kg",
        "kgs": "kg",
        "g": "g",
        "gr": "g",
        "gram": "g",
        "grams": "g",
        "lb": "lb",
        "lbs": "lb",
        "pound": "lb",
        "pounds": "lb",
        "oz": "oz",
        "ml": "ml",
        "milliliter": "ml",
        "milliliters": "ml",
        "l": "l",
        "lt": "l",
        "ltr": "l",
        "liter": "l",
        "liters": "l",
        "litre": "l",
        "litres": "l",
        "cl": "cl",
        "count": "count",
        "ct": "count",
        "pc": "count",
        "pcs": "count",
        "piece": "count",
        "pieces": "count",
        "unit": "count",
        "units": "count",
        "capsule": "capsule",
        "capsules": "capsule",
        "tablet": "tablet",
        "tablets": "tablet",
        "pod": "pod",
        "pods": "pod",
        "bag": "bag",
        "bags": "bag",
        "cm": "cm",
        "mm": "mm",
        "inch": "in",
        "inches": "in",
        "in": "in",
    }
    return mapping.get(unit.casefold().strip(), unit.casefold().strip())


def confidence_score(hits: int, max_hits: int) -> float:
    if max_hits <= 0:
        return 0.0
    score = hits / max_hits
    return round(min(1.0, max(0.0, score)), 2)
