from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse


AMAZON_ASIN_PATTERN = re.compile(r"^[A-Z0-9]{10}$")
AMAZON_HOST_PATTERN = re.compile(r"(amazon\.[a-z.]+)$", re.IGNORECASE)


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


def canonicalize_amazon_product_url(url: str | None) -> str | None:
    """Return a clean canonical Amazon product URL when an ASIN is present."""

    asin = extract_amazon_asin_from_url(url)
    if asin is None:
        return None

    host = _canonical_amazon_host(url)
    if host is None:
        return None

    return f"https://{host}/dp/{asin}"


def normalize_asin(value: Any) -> str | None:
    if value is None:
        return None
    candidate = str(value).strip().upper()
    if not candidate:
        return None
    if not AMAZON_ASIN_PATTERN.fullmatch(candidate):
        return None
    return candidate


def _canonical_amazon_host(url: str | None) -> str | None:
    if not url:
        return None

    try:
        parsed = urlparse(url)
    except ValueError:
        return None

    hostname = (parsed.hostname or "").casefold()
    if not hostname or "amazon." not in hostname:
        return None

    match = AMAZON_HOST_PATTERN.search(hostname)
    if match is None:
        return None

    return f"www.{match.group(1).lower()}"
