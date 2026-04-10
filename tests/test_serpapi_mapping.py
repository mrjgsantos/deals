from __future__ import annotations

import csv
from io import StringIO

from app.ingestion.parsers.affiliate_feed import AffiliateFeedCSVParser
from scripts.ingest_serpapi_google_shopping import to_affiliate_csv


def _parse_single_row(csv_payload: str):
    return next(csv.DictReader(StringIO(csv_payload)))


def test_serpapi_mapping_marks_google_redirect_links_with_medium_merchant_confidence() -> None:
    csv_payload, mapped_count = to_affiliate_csv(
        [
            {
                "title": "Wireless Earbuds",
                "product_link": "https://www.google.com/shopping/product/123456",
                "price": "$59.99",
                "source": "Example Store",
                "thumbnail": "https://example.com/image.jpg",
            }
        ],
        limit=5,
    )

    assert mapped_count == 1
    row = _parse_single_row(csv_payload)
    assert row["source_link_type"] == "google_redirect"
    assert row["is_google_redirect"] == "true"
    assert row["merchant_confidence"] == "medium"

    parsed = AffiliateFeedCSVParser().parse(csv_payload)[0]
    assert parsed.merchant_name == "Example Store"
    assert parsed.source_attributes["source_link_type"] == "google_redirect"
    assert parsed.source_attributes["is_google_redirect"] is True
    assert parsed.source_attributes["merchant_confidence"] == "medium"


def test_serpapi_mapping_marks_direct_links_with_high_merchant_confidence() -> None:
    csv_payload, mapped_count = to_affiliate_csv(
        [
            {
                "title": "Air Fryer",
                "product_link": "https://www.bestbuy.com/site/example-product/123.p",
                "price": "$129.99",
                "source": "Best Buy",
                "thumbnail": "https://example.com/image.jpg",
            }
        ],
        limit=5,
    )

    assert mapped_count == 1
    row = _parse_single_row(csv_payload)
    assert row["source_link_type"] == "direct_merchant"
    assert row["is_google_redirect"] == "false"
    assert row["merchant_confidence"] == "high"


def test_serpapi_mapping_falls_back_to_merchant_name_label_source() -> None:
    csv_payload, mapped_count = to_affiliate_csv(
        [
            {
                "title": "Robot Vacuum",
                "product_link": "https://merchant.example.com/products/robot-vacuum",
                "price": "$299.99",
                "merchant_name": "Merchant Example",
                "thumbnail": "https://example.com/image.jpg",
            }
        ],
        limit=5,
    )

    assert mapped_count == 1
    row = _parse_single_row(csv_payload)
    assert row["merchant"] == "Merchant Example"
    assert row["merchant_label_source"] == "merchant_name"

    parsed = AffiliateFeedCSVParser().parse(csv_payload)[0]
    assert parsed.merchant_name == "Merchant Example"
    assert parsed.source_attributes["merchant_label_source"] == "merchant_name"
