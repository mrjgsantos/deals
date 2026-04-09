from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.pricing.aggregation import aggregate_price_history, build_daily_price_statistics
from app.pricing.schemas import PricePoint


def test_aggregate_price_history_windows_and_days_at_current_price() -> None:
    now = datetime(2026, 4, 8, tzinfo=UTC)
    price_points = [
        PricePoint(observed_at=now - timedelta(days=120), sale_price=Decimal("120.00")),
        PricePoint(observed_at=now - timedelta(days=80), sale_price=Decimal("110.00")),
        PricePoint(observed_at=now - timedelta(days=20), sale_price=Decimal("100.00")),
        PricePoint(observed_at=now - timedelta(days=2), sale_price=Decimal("90.00")),
        PricePoint(observed_at=now - timedelta(days=1), sale_price=Decimal("90.00")),
        PricePoint(observed_at=now, sale_price=Decimal("90.00")),
    ]

    aggregation = aggregate_price_history(price_points, now=now)

    assert aggregation.current_price == Decimal("90.00")
    assert aggregation.avg_30d == Decimal("93.33")
    assert aggregation.avg_90d == Decimal("97.50")
    assert aggregation.min_90d == Decimal("90.00")
    assert aggregation.max_90d == Decimal("110.00")
    assert aggregation.all_time_min == Decimal("90.00")
    assert aggregation.all_time_max == Decimal("120.00")
    assert aggregation.days_at_current_price == 3


def test_build_daily_price_statistics_averages_multiple_points_same_day() -> None:
    now = datetime(2026, 4, 8, 12, 0, tzinfo=UTC)
    price_points = [
        PricePoint(observed_at=now.replace(hour=8), sale_price=Decimal("100.00")),
        PricePoint(observed_at=now.replace(hour=12), sale_price=Decimal("90.00")),
        PricePoint(observed_at=now - timedelta(days=1), sale_price=Decimal("80.00")),
    ]

    daily = build_daily_price_statistics(price_points)

    assert daily[now.date()] == Decimal("95.00")
    assert daily[(now - timedelta(days=1)).date()] == Decimal("80.00")
