from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse


AMAZON_ASIN_PATTERN = re.compile(r"^[A-Z0-9]{10}$")


def extract_amazon_asin_from_url(url: str | None) -> str | None:
    """Extract an ASIN only from clear Amazon product URL patterns."""

    if not url:
        return None

    try:
        parsed = urlparse(url)
    except ValueError:
        return None

    host = (parsed.netloc or "").casefold()
    if "amazon." not in host:
        return None

    parts = [part for part in parsed.path.split("/") if part]
    for index, part in enumerate(parts[:-1]):
        if part in {"dp", "gp", "product"}:
            candidate = parts[index + 1].upper()
            if AMAZON_ASIN_PATTERN.fullmatch(candidate):
                return candidate

    for offset, part in enumerate(parts[:-1]):
        if part == "gp" and offset + 2 < len(parts) and parts[offset + 1] == "product":
            candidate = parts[offset + 2].upper()
            if AMAZON_ASIN_PATTERN.fullmatch(candidate):
                return candidate

    return None


def normalize_asin(value: Any) -> str | None:
    if value is None:
        return None
    candidate = str(value).strip().upper()
    if not candidate:
        return None
    if not AMAZON_ASIN_PATTERN.fullmatch(candidate):
        return None
    return candidate
