from __future__ import annotations

from app.ingestion.amazon_identifiers import canonicalize_amazon_product_url, extract_amazon_asin_from_url


def test_extract_amazon_asin_from_dp_url() -> None:
    assert extract_amazon_asin_from_url("https://www.amazon.es/dp/B0TEST1234") == "B0TEST1234"


def test_extract_amazon_asin_returns_none_for_non_amazon_url() -> None:
    assert extract_amazon_asin_from_url("https://example.com/dp/B0TEST1234") is None


def test_extract_amazon_asin_returns_none_for_malformed_url() -> None:
    assert extract_amazon_asin_from_url("not a url at all") is None


def test_canonicalize_amazon_product_url_strips_tracking_junk() -> None:
    assert (
        canonicalize_amazon_product_url(
            "https://www.amazon.es/Example-Product/dp/B0TEST1234/ref=sr_1_1?tag=partner-21&psc=1"
        )
        == "https://www.amazon.es/dp/B0TEST1234"
    )


def test_canonicalize_amazon_product_url_normalizes_gp_product_path() -> None:
    assert (
        canonicalize_amazon_product_url("https://www.amazon.es/gp/product/B0TEST1234?smid=A1TEST&th=1")
        == "https://www.amazon.es/dp/B0TEST1234"
    )


def test_canonicalize_amazon_product_url_preserves_amazon_marketplace_host() -> None:
    assert (
        canonicalize_amazon_product_url("https://smile.amazon.co.uk/dp/B0TEST1234?ref_=abc")
        == "https://www.amazon.co.uk/dp/B0TEST1234"
    )
