from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from app.integrations.keepa_history import extract_keepa_price_points

DOMAIN_CURRENCY_MAP: dict[int, str] = {
    1: "USD",
    2: "GBP",
    3: "EUR",
    4: "EUR",
    5: "JPY",
    6: "CAD",
    8: "EUR",
    9: "EUR",
    10: "INR",
}

DOMAIN_HOST_MAP: dict[int, str] = {
    1: "amazon.com",
    2: "amazon.co.uk",
    3: "amazon.de",
    4: "amazon.fr",
    5: "amazon.co.jp",
    6: "amazon.ca",
    8: "amazon.it",
    9: "amazon.es",
    10: "amazon.in",
}


def normalize_keepa_payload_for_ingest(
    payload: dict[str, Any],
    *,
    domain_id: int | None = None,
) -> dict[str, Any]:
    """Fill the minimum parser-compatible fields on raw Keepa product payloads."""

    products = payload.get("products")
    if not isinstance(products, list):
        return payload

    normalized_payload = dict(payload)
    normalized_payload["products"] = [
        normalize_keepa_product_for_ingest(product, default_domain_id=domain_id)
        for product in products
        if isinstance(product, dict)
    ]
    return normalized_payload


def normalize_keepa_product_for_ingest(
    product: dict[str, Any],
    *,
    default_domain_id: int | None = None,
) -> dict[str, Any]:
    normalized = dict(product)
    resolved_domain_id = _resolved_domain_id(normalized.get("domainId"), default_domain_id=default_domain_id)
    normalized["domainId"] = resolved_domain_id
    if not str(normalized.get("productURL") or "").strip():
        product_url = _built_product_url(normalized, domain_id=resolved_domain_id)
        if product_url is not None:
            normalized["productURL"] = product_url

    if not str(normalized.get("currency") or "").strip():
        normalized["currency"] = DOMAIN_CURRENCY_MAP.get(resolved_domain_id, "USD")

    current_price_cents = _current_price_cents(normalized)
    if _positive_cents(normalized.get("buyBoxPrice")) is None and current_price_cents is not None:
        normalized["buyBoxPrice"] = current_price_cents
    if _positive_cents(normalized.get("newPrice")) is None and current_price_cents is not None:
        normalized["newPrice"] = current_price_cents
    if _positive_cents(normalized.get("lastPrice")) is None and current_price_cents is not None:
        normalized["lastPrice"] = current_price_cents

    list_price_cents = _history_price_cents(normalized, history_key="LISTPRICE")
    if _positive_cents(normalized.get("listPrice")) is None and list_price_cents is not None:
        normalized["listPrice"] = list_price_cents

    return normalized


def keepa_product_ingest_rejection_reason(product: dict[str, Any]) -> str | None:
    title = str(product.get("title") or "").strip()
    if not title:
        return "missing_title"

    current_price_cents = _current_price_cents(product)
    if current_price_cents is None:
        return "missing_current_price"

    return None


def _resolved_domain_id(raw_domain_id: object, *, default_domain_id: int | None) -> int:
    try:
        if raw_domain_id is not None:
            return int(raw_domain_id)
    except (TypeError, ValueError):
        pass
    return int(default_domain_id or 1)


def _built_product_url(product: dict[str, Any], *, domain_id: int) -> str | None:
    asin = str(product.get("asin") or "").strip().upper()
    if not asin:
        return None
    host = DOMAIN_HOST_MAP.get(domain_id, "amazon.com")
    return f"https://www.{host}/dp/{asin}"


def _current_price_cents(product: dict[str, Any]) -> int | None:
    direct_keys = ("buyBoxPrice", "newPrice", "lastPrice")
    for key in direct_keys:
        cents = _positive_cents(product.get(key))
        if cents is not None:
            return cents

    for history_key in ("NEW", "AMAZON"):
        cents = _history_price_cents(product, history_key=history_key)
        if cents is not None:
            return cents
    return None


def _history_price_cents(product: dict[str, Any], *, history_key: str) -> int | None:
    points = extract_keepa_price_points(product, history_key=history_key)
    if not points:
        return None
    last_price = points[-1].sale_price
    return int((last_price * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _positive_cents(value: object) -> int | None:
    try:
        numeric = int(value)
    except (TypeError, ValueError):
        return None
    if numeric <= 0:
        return None
    return numeric
