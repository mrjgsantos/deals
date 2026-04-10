from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from app.pricing.schemas import PricePoint

KEEPA_EPOCH = datetime(2011, 1, 1, tzinfo=UTC)

# Raw Keepa REST payloads expose history in csv[index] alternating
# [keepa_minutes, value, keepa_minutes, value, ...].
# These low indexes are stable across common Keepa clients and cover
# the history types we need first.
KEEPA_CSV_HISTORY_INDEX: dict[str, int] = {
    "AMAZON": 0,
    "NEW": 1,
    "USED": 2,
    "SALES": 3,
    "LISTPRICE": 4,
}


@dataclass(slots=True)
class KeepaHistorySummary:
    min_price: Decimal | None
    avg_price: Decimal | None
    observation_count: int


def keepa_minutes_to_datetime(value: Any) -> datetime | None:
    """Convert Keepa minutes since 2011-01-01 UTC to a UTC datetime."""

    try:
        minutes = int(value)
    except (TypeError, ValueError):
        return None
    return KEEPA_EPOCH + timedelta(minutes=minutes)


def keepa_price_to_decimal(value: Any) -> Decimal | None:
    """Convert Keepa integer cents to a positive decimal price."""

    try:
        numeric = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None

    if numeric <= 0:
        return None
    return (numeric / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def extract_keepa_price_points(
    product: dict[str, Any],
    *,
    history_key: str = "NEW",
) -> list[PricePoint]:
    """Extract normalized price points from a Keepa product payload."""

    history_name = history_key.upper()
    points = _extract_from_data_history(product, history_name)
    if points:
        return points
    return _extract_from_csv_history(product, history_name)


def summarize_keepa_price_points(price_points: list[PricePoint]) -> KeepaHistorySummary:
    if not price_points:
        return KeepaHistorySummary(min_price=None, avg_price=None, observation_count=0)

    prices = [point.sale_price for point in price_points]
    avg_price = (sum(prices) / Decimal(len(prices))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return KeepaHistorySummary(
        min_price=min(prices),
        avg_price=avg_price,
        observation_count=len(price_points),
    )


def _extract_from_data_history(product: dict[str, Any], history_name: str) -> list[PricePoint]:
    data = product.get("data")
    if not isinstance(data, dict):
        return []

    prices = data.get(history_name)
    times = data.get(f"{history_name}_time")
    if not isinstance(prices, list) or not isinstance(times, list):
        return []

    points = [
        PricePoint(observed_at=observed_at, sale_price=sale_price)
        for observed_at, sale_price in (
            (keepa_minutes_to_datetime(observed_raw), keepa_price_to_decimal(price_raw))
            for observed_raw, price_raw in zip(times, prices)
        )
        if observed_at is not None and sale_price is not None
    ]
    return sorted(points, key=lambda point: point.observed_at)


def _extract_from_csv_history(product: dict[str, Any], history_name: str) -> list[PricePoint]:
    csv_history = product.get("csv")
    if not isinstance(csv_history, list):
        return []

    index = KEEPA_CSV_HISTORY_INDEX.get(history_name)
    if index is None or index >= len(csv_history):
        return []

    raw_series = csv_history[index]
    if not isinstance(raw_series, list):
        return []

    points: list[PricePoint] = []
    for offset in range(0, len(raw_series) - 1, 2):
        observed_at = keepa_minutes_to_datetime(raw_series[offset])
        sale_price = keepa_price_to_decimal(raw_series[offset + 1])
        if observed_at is None or sale_price is None:
            continue
        points.append(PricePoint(observed_at=observed_at, sale_price=sale_price))

    return sorted(points, key=lambda point: point.observed_at)
