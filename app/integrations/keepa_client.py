from __future__ import annotations

from typing import Any

import httpx

from app.core.config import settings

KEEPA_PRODUCT_ENDPOINT = "https://api.keepa.com/product"


class KeepaClientError(RuntimeError):
    """Raised when Keepa cannot provide a usable product payload."""


class KeepaConfigurationError(KeepaClientError):
    """Raised when local Keepa client configuration is incomplete."""


async def fetch_products_by_asins(
    asins: list[str],
    *,
    domain_id: int | None = None,
    timeout: float = 30.0,
    http_client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Fetch one or more Keepa product payloads by ASIN with history enabled."""

    normalized_asins = _normalize_asins(asins)
    if not normalized_asins:
        raise KeepaClientError("missing_asin")

    params = _build_keepa_request_params(normalized_asins, domain_id=domain_id)

    owns_client = http_client is None
    client = http_client or httpx.AsyncClient(timeout=timeout)
    try:
        response = await client.get(KEEPA_PRODUCT_ENDPOINT, params=params)
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise KeepaClientError(f"keepa_http_error:{exc.response.status_code}") from exc
    except httpx.RequestError as exc:
        raise KeepaClientError("keepa_request_error") from exc
    finally:
        if owns_client:
            await client.aclose()

    try:
        payload = response.json()
    except ValueError as exc:
        raise KeepaClientError("keepa_invalid_json") from exc

    return _validate_keepa_payload(payload)


async def fetch_product_by_asin(
    asin: str,
    *,
    domain_id: int | None = None,
    timeout: float = 30.0,
    http_client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Fetch a single Keepa product payload by ASIN with history enabled."""

    return await fetch_products_by_asins(
        [asin],
        domain_id=domain_id,
        timeout=timeout,
        http_client=http_client,
    )


def _build_keepa_request_params(asins: list[str], *, domain_id: int | None) -> dict[str, Any]:
    api_key = (settings.keepa_api_key or "").strip()
    if not api_key:
        raise KeepaConfigurationError("missing_keepa_api_key")

    keepa_domain_id = domain_id if domain_id is not None else settings.keepa_domain_id
    return {
        "key": api_key,
        "domain": keepa_domain_id,
        "asin": ",".join(asins),
        "buybox": 1,
        "history": 1,
        "stats": 90,
    }


def _normalize_asins(asins: list[str]) -> list[str]:
    normalized: list[str] = []
    for asin in asins:
        candidate = asin.strip().upper()
        if candidate and candidate not in normalized:
            normalized.append(candidate)
    return normalized


def _validate_keepa_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise KeepaClientError("keepa_invalid_payload")

    if payload.get("error"):
        raise KeepaClientError("keepa_error_response")

    products = payload.get("products")
    if not isinstance(products, list):
        raise KeepaClientError("keepa_missing_products")

    if not any(isinstance(product, dict) for product in products):
        if _looks_rate_limited(payload):
            raise KeepaClientError("keepa_rate_limited")
        raise KeepaClientError("keepa_empty_products")

    return payload


def _looks_rate_limited(payload: dict[str, Any]) -> bool:
    tokens_left = payload.get("tokensLeft")
    refill_in = payload.get("refillIn")
    try:
        if tokens_left is not None and int(tokens_left) <= 0:
            return True
    except (TypeError, ValueError):
        pass
    try:
        if refill_in is not None and int(refill_in) > 0:
            return True
    except (TypeError, ValueError):
        pass
    return False
