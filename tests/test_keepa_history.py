from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from app.integrations.keepa_history import (
    extract_keepa_price_points,
    keepa_minutes_to_datetime,
    keepa_price_to_decimal,
    summarize_keepa_price_points,
)


def test_keepa_minutes_to_datetime_converts_from_keepa_epoch() -> None:
    assert keepa_minutes_to_datetime(0) == datetime(2011, 1, 1, tzinfo=UTC)
    assert keepa_minutes_to_datetime(60) == datetime(2011, 1, 1, 1, 0, tzinfo=UTC)


def test_keepa_price_to_decimal_converts_cents_and_rejects_invalid_values() -> None:
    assert keepa_price_to_decimal(4299) == Decimal("42.99")
    assert keepa_price_to_decimal("199") == Decimal("1.99")
    assert keepa_price_to_decimal(0) is None
    assert keepa_price_to_decimal(-1) is None
    assert keepa_price_to_decimal("nope") is None


def test_extract_keepa_price_points_from_data_dict_shape() -> None:
    product = {
        "data": {
            "NEW": [4299, 3899, -1, 3599],
            "NEW_time": [0, 60, 120, 180],
        }
    }

    points = extract_keepa_price_points(product, history_key="NEW")

    assert [(point.observed_at, point.sale_price) for point in points] == [
        (datetime(2011, 1, 1, 0, 0, tzinfo=UTC), Decimal("42.99")),
        (datetime(2011, 1, 1, 1, 0, tzinfo=UTC), Decimal("38.99")),
        (datetime(2011, 1, 1, 3, 0, tzinfo=UTC), Decimal("35.99")),
    ]


def test_extract_keepa_price_points_from_raw_csv_shape() -> None:
    product = {
        "csv": [
            [],
            [0, 4299, 60, 3899, 120, -1, 180, 3599],
        ]
    }

    points = extract_keepa_price_points(product, history_key="NEW")

    assert [(point.observed_at, point.sale_price) for point in points] == [
        (datetime(2011, 1, 1, 0, 0, tzinfo=UTC), Decimal("42.99")),
        (datetime(2011, 1, 1, 1, 0, tzinfo=UTC), Decimal("38.99")),
        (datetime(2011, 1, 1, 3, 0, tzinfo=UTC), Decimal("35.99")),
    ]


def test_extract_keepa_price_points_returns_empty_for_missing_or_invalid_history() -> None:
    assert extract_keepa_price_points({}, history_key="NEW") == []
    assert extract_keepa_price_points({"data": {"NEW": [], "NEW_time": []}}, history_key="NEW") == []
    assert extract_keepa_price_points({"csv": [None, ["bad", "data"]]}, history_key="NEW") == []


def test_summarize_keepa_price_points_returns_min_avg_and_count() -> None:
    points = extract_keepa_price_points(
        {
            "data": {
                "NEW": [5000, 4000, 3000],
                "NEW_time": [0, 60, 120],
            }
        }
    )

    summary = summarize_keepa_price_points(points)

    assert summary.min_price == Decimal("30.00")
    assert summary.avg_price == Decimal("40.00")
    assert summary.observation_count == 3
