from __future__ import annotations

from app.ingestion.amazon_identifiers import extract_amazon_asin_from_url


def test_extract_amazon_asin_from_dp_url() -> None:
    assert extract_amazon_asin_from_url("https://www.amazon.es/dp/B0TEST1234") == "B0TEST1234"


def test_extract_amazon_asin_returns_none_for_non_amazon_url() -> None:
    assert extract_amazon_asin_from_url("https://example.com/dp/B0TEST1234") is None


def test_extract_amazon_asin_returns_none_for_malformed_url() -> None:
    assert extract_amazon_asin_from_url("not a url at all") is None
