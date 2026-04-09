from __future__ import annotations

from decimal import Decimal

from app.pricing.fake_discount import analyze_fake_discount
from app.pricing.schemas import PriceAggregation


def make_aggregation(**overrides) -> PriceAggregation:
    data = {
        "current_price": Decimal("80.00"),
        "avg_30d": Decimal("100.00"),
        "avg_90d": Decimal("95.00"),
        "min_90d": Decimal("70.00"),
        "max_90d": Decimal("110.00"),
        "all_time_min": Decimal("65.00"),
        "all_time_max": Decimal("120.00"),
        "days_at_current_price": 2,
        "observation_count_30d": 20,
        "observation_count_90d": 60,
        "observation_count_all_time": 100,
    }
    data.update(overrides)
    return PriceAggregation(**data)


def test_flag_claimed_old_price_never_observed() -> None:
    analysis = analyze_fake_discount(
        current_price=Decimal("80.00"),
        claimed_old_price=Decimal("150.00"),
        claimed_discount_percent=Decimal("46.67"),
        aggregation=make_aggregation(),
    )

    assert analysis.is_fake_discount is True
    assert any(flag.code == "claimed_old_price_never_observed" for flag in analysis.flags)


def test_flag_current_sale_price_active_too_long() -> None:
    analysis = analyze_fake_discount(
        current_price=Decimal("80.00"),
        claimed_old_price=Decimal("100.00"),
        claimed_discount_percent=Decimal("20.00"),
        aggregation=make_aggregation(days_at_current_price=30),
    )

    assert analysis.is_fake_discount is True
    assert any(flag.code == "current_sale_price_active_too_long" for flag in analysis.flags)


def test_flag_current_price_above_historical_average() -> None:
    analysis = analyze_fake_discount(
        current_price=Decimal("105.00"),
        claimed_old_price=Decimal("130.00"),
        claimed_discount_percent=Decimal("19.23"),
        aggregation=make_aggregation(current_price=Decimal("105.00"), avg_90d=Decimal("95.00")),
    )

    assert analysis.is_fake_discount is True
    assert any(flag.code == "current_price_above_historical_average" for flag in analysis.flags)


def test_flag_discount_math_inconsistent() -> None:
    analysis = analyze_fake_discount(
        current_price=Decimal("80.00"),
        claimed_old_price=Decimal("100.00"),
        claimed_discount_percent=Decimal("50.00"),
        aggregation=make_aggregation(),
    )

    assert analysis.is_fake_discount is True
    assert any(flag.code == "claimed_discount_math_inconsistent" for flag in analysis.flags)
