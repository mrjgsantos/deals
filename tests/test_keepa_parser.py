from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from app.ingestion.parsers.keepa import KeepaParser


def test_keepa_parser_converts_last_update_from_keepa_epoch_minutes() -> None:
    parser = KeepaParser()
    payload = {
        "products": [
            {
                "asin": "B0TEST1234",
                "domainId": 9,
                "title": "Example Product",
                "brand": "Example",
                "manufacturer": "Example",
                "currency": "EUR",
                "newPrice": 4999,
                "listPrice": 6999,
                "availabilityAmazon": 1,
                "lastUpdate": 8000000,
                "csv": [[], [7999800, 6999, 7999920, 6499, 7999980, 4999]],
            }
        ]
    }

    records = parser.parse(payload)

    assert len(records) == 1
    assert records[0].observed_at == datetime(2026, 3, 18, 13, 20, tzinfo=UTC)
    assert records[0].current_price == Decimal("49.99")
    assert records[0].source_attributes["asin"] == "B0TEST1234"
    assert records[0].raw_payload["csv"][1][-2:] == [7999980, 4999]


def test_keepa_parser_accepts_raw_keepa_csv_payload_without_flat_price_fields() -> None:
    parser = KeepaParser()
    payload = {
        "products": [
            {
                "asin": "B0RAW12345",
                "domainId": 9,
                "title": "Raw Keepa Product",
                "brand": "Example",
                "manufacturer": "Example",
                "lastUpdate": 8000000,
                "csv": [
                    [],
                    [7999800, 6999, 7999920, 6499, 7999980, 4999],
                    [],
                    [],
                    [7999800, 8999],
                ],
            }
        ]
    }

    records = parser.parse(payload)

    assert len(records) == 1
    assert records[0].currency == "EUR"
    assert records[0].current_price == Decimal("49.99")
    assert records[0].list_price == Decimal("89.99")
    assert records[0].product_url == "https://www.amazon.es/dp/B0RAW12345"
