from __future__ import annotations

from decimal import Decimal
from datetime import UTC, datetime

from app.db.enums import AvailabilityStatus
from app.ingestion.normalization import DefaultRecordNormalizer
from app.ingestion.parsers.affiliate_feed import AffiliateFeedCSVParser
from app.ingestion.schemas import ParsedSourceRecord


def test_normalizer_preserves_existing_asin() -> None:
    normalizer = DefaultRecordNormalizer()
    record = ParsedSourceRecord(
        external_id="sku-1",
        product_url="https://www.amazon.es/dp/B0SHOULDNOTUSE",
        title="Example Product",
        currency="EUR",
        current_price=Decimal("59.99"),
        availability_status=AvailabilityStatus.IN_STOCK,
        observed_at=datetime(2026, 4, 9, tzinfo=UTC),
        source_attributes={"asin": "B0TEST1234"},
        raw_payload={},
    )

    normalized = normalizer.normalize(record)

    assert normalized.source_attributes["asin"] == "B0TEST1234"


def test_normalizer_extracts_asin_from_amazon_product_url_when_missing() -> None:
    normalizer = DefaultRecordNormalizer()
    record = ParsedSourceRecord(
        external_id="sku-1",
        product_url="https://www.amazon.es/dp/B0TEST5678",
        title="Example Product",
        currency="EUR",
        current_price=Decimal("59.99"),
        availability_status=AvailabilityStatus.IN_STOCK,
        observed_at=datetime(2026, 4, 9, tzinfo=UTC),
        source_attributes={},
        raw_payload={},
    )

    normalized = normalizer.normalize(record)

    assert normalized.source_attributes["asin"] == "B0TEST5678"


def test_normalizer_does_not_extract_asin_from_non_amazon_url() -> None:
    normalizer = DefaultRecordNormalizer()
    record = ParsedSourceRecord(
        external_id="sku-1",
        product_url="https://example.com/dp/B0TEST5678",
        title="Example Product",
        currency="EUR",
        current_price=Decimal("59.99"),
        availability_status=AvailabilityStatus.IN_STOCK,
        observed_at=datetime(2026, 4, 9, tzinfo=UTC),
        source_attributes={},
        raw_payload={},
    )

    normalized = normalizer.normalize(record)

    assert normalized.source_attributes["asin"] is None


def test_affiliate_parser_preserves_payload_asin_when_present() -> None:
    parser = AffiliateFeedCSVParser()

    records = parser.parse(
        "id,url,title,price,currency,asin\n"
        "sku-1,https://www.amazon.es/dp/B0TEST5678,Example Product,59.99,EUR,b0test1234\n"
    )

    assert len(records) == 1
    assert records[0].source_attributes["asin"] == "B0TEST1234"
