from __future__ import annotations

import asyncio

import httpx
import pytest

from app.integrations.keepa_client import (
    KEEPA_PRODUCT_ENDPOINT,
    KeepaClientError,
    KeepaConfigurationError,
    fetch_products_by_asins,
    fetch_product_by_asin,
)


class FakeResponse:
    def __init__(self, payload, *, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code
        self.request = httpx.Request("GET", KEEPA_PRODUCT_ENDPOINT)

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "boom",
                request=self.request,
                response=httpx.Response(self.status_code, request=self.request),
            )

    def json(self):
        return self._payload


class FakeAsyncClient:
    def __init__(self, response):
        self.response = response
        self.calls = []
        self.closed = False

    async def get(self, url, params):
        self.calls.append((url, params))
        return self.response

    async def aclose(self):
        self.closed = True


def test_fetch_product_by_asin_raises_when_api_key_missing(monkeypatch) -> None:
    monkeypatch.setattr("app.integrations.keepa_client.settings.keepa_api_key", None)

    with pytest.raises(KeepaConfigurationError, match="missing_keepa_api_key"):
        asyncio.run(fetch_product_by_asin("B0TEST1234"))


def test_fetch_product_by_asin_uses_expected_request_shape(monkeypatch) -> None:
    monkeypatch.setattr("app.integrations.keepa_client.settings.keepa_api_key", "test-key")
    monkeypatch.setattr("app.integrations.keepa_client.settings.keepa_domain_id", 3)
    client = FakeAsyncClient(FakeResponse({"products": [{"asin": "B0TEST1234"}], "tokensLeft": 42}))

    payload = asyncio.run(fetch_product_by_asin("b0test1234", http_client=client))

    assert payload["products"][0]["asin"] == "B0TEST1234"
    assert client.calls == [
        (
            KEEPA_PRODUCT_ENDPOINT,
            {
                "key": "test-key",
                "domain": 3,
                "asin": "B0TEST1234",
                "buybox": 1,
                "history": 1,
                "stats": 90,
            },
        )
    ]


def test_fetch_products_by_asins_uses_expected_request_shape(monkeypatch) -> None:
    monkeypatch.setattr("app.integrations.keepa_client.settings.keepa_api_key", "test-key")
    monkeypatch.setattr("app.integrations.keepa_client.settings.keepa_domain_id", 9)
    client = FakeAsyncClient(FakeResponse({"products": [{"asin": "B0TEST1234"}], "tokensLeft": 42}))

    payload = asyncio.run(fetch_products_by_asins(["b0test1234", "B0TEST5678", "b0test1234"], http_client=client))

    assert payload["products"][0]["asin"] == "B0TEST1234"
    assert client.calls == [
        (
            KEEPA_PRODUCT_ENDPOINT,
            {
                "key": "test-key",
                "domain": 9,
                "asin": "B0TEST1234,B0TEST5678",
                "buybox": 1,
                "history": 1,
                "stats": 90,
            },
        )
    ]


def test_fetch_product_by_asin_rejects_empty_products(monkeypatch) -> None:
    monkeypatch.setattr("app.integrations.keepa_client.settings.keepa_api_key", "test-key")
    client = FakeAsyncClient(FakeResponse({"products": []}))

    with pytest.raises(KeepaClientError, match="keepa_empty_products"):
        asyncio.run(fetch_product_by_asin("B0TEST1234", http_client=client))


def test_fetch_product_by_asin_rejects_rate_limited_empty_response(monkeypatch) -> None:
    monkeypatch.setattr("app.integrations.keepa_client.settings.keepa_api_key", "test-key")
    client = FakeAsyncClient(FakeResponse({"products": [], "tokensLeft": 0, "refillIn": 60000}))

    with pytest.raises(KeepaClientError, match="keepa_rate_limited"):
        asyncio.run(fetch_product_by_asin("B0TEST1234", http_client=client))
