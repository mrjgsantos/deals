from __future__ import annotations

import re
from dataclasses import dataclass

from app.ingestion.variant_helpers import normalize_variant_text


COLOR_ALIASES = {
    "black": "black",
    "white": "white",
    "red": "red",
    "blue": "blue",
    "green": "green",
    "yellow": "yellow",
    "silver": "silver",
    "gold": "gold",
    "gray": "gray",
    "grey": "gray",
    "pink": "pink",
    "orange": "orange",
    "purple": "purple",
    "brown": "brown",
    "beige": "beige",
    "ivory": "ivory",
    "navy": "navy",
}
GENERATION_TOKENS = {"gen", "generation", "1st", "2nd", "3rd", "4th", "5th", "6th"}
ORDINAL_SUFFIX_TOKENS = {"st", "nd", "rd", "th"}
MODEL_STOPWORDS = {
    "with",
    "pack",
    "of",
    "set",
    "bundle",
    "case",
    "cover",
    "wireless",
    "bluetooth",
}
PACK_COUNT_RE = re.compile(
    r"\b(?:pack of\s*(?P<of>\d+)|(?P<dash>\d+)\s*-\s*pack|(?P<loose>\d+)\s+pack|(?P<prefix>\d+)\s*(?:pack|pk)\b)\b"
)
STORAGE_RE = re.compile(r"\b(?P<amount>\d+)\s*(?P<unit>g\s*b|t\s*b|m\s*b|gb|tb|mb)\b")
TOKEN_RE = re.compile(r"[a-z0-9]+")
PRECISE_MODEL_RE = re.compile(r"\b[a-z]{1,5}-\d{2,5}[a-z]{1,5}\d?\b")


@dataclass
class TitleNormalizationFeatures:
    normalized_title: str
    normalized_brand: str | None = None
    normalized_model: str | None = None
    normalized_color: str | None = None
    normalized_storage: str | None = None
    normalized_pack_count: int | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "normalized_title": self.normalized_title,
            "normalized_brand": self.normalized_brand,
            "normalized_model": self.normalized_model,
            "normalized_color": self.normalized_color,
            "normalized_storage": self.normalized_storage,
            "normalized_pack_count": self.normalized_pack_count,
        }


def extract_title_normalization_features(title: str, *, brand: str | None = None) -> TitleNormalizationFeatures:
    stripped_title = _strip_weak_punctuation(title)
    normalized_title = normalize_variant_text(stripped_title)
    normalized_brand = _normalize_brand(brand)
    normalized_storage = _extract_storage(normalized_title)
    normalized_pack_count = _extract_pack_count(normalized_title)
    normalized_color = _extract_color(normalized_title)
    normalized_model = _extract_model(
        stripped_title.casefold(),
        normalized_title,
        normalized_brand=normalized_brand,
        normalized_storage=normalized_storage,
        normalized_color=normalized_color,
    )

    return TitleNormalizationFeatures(
        normalized_title=normalized_title,
        normalized_brand=normalized_brand,
        normalized_model=normalized_model,
        normalized_color=normalized_color,
        normalized_storage=normalized_storage,
        normalized_pack_count=normalized_pack_count,
    )


def _strip_weak_punctuation(value: str) -> str:
    cleaned = re.sub(r"[(){}\[\],;/]+", " ", value)
    cleaned = cleaned.replace("'", "")
    cleaned = cleaned.replace('"', " ")
    cleaned = cleaned.replace(":", " ")
    return cleaned


def _normalize_brand(brand: str | None) -> str | None:
    if not brand:
        return None
    normalized = normalize_variant_text(_strip_weak_punctuation(brand))
    return normalized or None


def _extract_storage(normalized_title: str) -> str | None:
    match = STORAGE_RE.search(normalized_title)
    if not match:
        return None
    amount = match.group("amount")
    unit = match.group("unit").replace(" ", "")
    return f"{amount}{unit}"


def _extract_pack_count(normalized_title: str) -> int | None:
    match = PACK_COUNT_RE.search(normalized_title)
    if not match:
        return None
    raw = match.group("of") or match.group("dash") or match.group("loose") or match.group("prefix")
    return int(raw) if raw else None


def _extract_color(normalized_title: str) -> str | None:
    for token in TOKEN_RE.findall(normalized_title):
        normalized = COLOR_ALIASES.get(token)
        if normalized:
            return normalized
    return None


def _extract_model(
    raw_title: str,
    normalized_title: str,
    *,
    normalized_brand: str | None,
    normalized_storage: str | None,
    normalized_color: str | None,
) -> str | None:
    precise_model_match = PRECISE_MODEL_RE.search(raw_title)
    if precise_model_match:
        return precise_model_match.group(0)

    tokens = TOKEN_RE.findall(normalized_title)
    if not tokens:
        return None

    brand_tokens = set(TOKEN_RE.findall(normalized_brand)) if normalized_brand else set()
    storage_tokens = set(TOKEN_RE.findall(normalized_storage)) if normalized_storage else set()
    model_tokens: list[str] = []

    for index, token in enumerate(tokens):
        next_token = tokens[index + 1] if index + 1 < len(tokens) else None
        if token.isdigit() and next_token and f"{token}{next_token}" == normalized_storage:
            break
        if storage_tokens and token in storage_tokens:
            break
        if normalized_color and token == normalized_color:
            break
        if _starts_generation_sequence(tokens, index):
            break
        if token in MODEL_STOPWORDS:
            break
        if token in {"pack", "pk", "set", "bundle"}:
            break
        if token.isdigit() and not model_tokens:
            return None
        if brand_tokens and token in brand_tokens and not model_tokens:
            continue
        model_tokens.append(token)
        if len(model_tokens) >= 3:
            break

    if not model_tokens:
        return None
    if not any(any(char.isdigit() for char in token) for token in model_tokens):
        if _contains_generation_signal(tokens) and len(model_tokens) >= 2:
            return "-".join(model_tokens)
        return None
    if len(model_tokens) == 1 and model_tokens[0].isdigit():
        return None
    return "-".join(model_tokens)


def _starts_generation_sequence(tokens: list[str], index: int) -> bool:
    token = tokens[index]
    if token in GENERATION_TOKENS:
        return True
    next_token = tokens[index + 1] if index + 1 < len(tokens) else None
    next_next_token = tokens[index + 2] if index + 2 < len(tokens) else None
    return bool(
        token.isdigit()
        and next_token in ORDINAL_SUFFIX_TOKENS
        and next_next_token in {"gen", "generation"}
    )


def _contains_generation_signal(tokens: list[str]) -> bool:
    return any(_starts_generation_sequence(tokens, index) for index in range(len(tokens)))
