from __future__ import annotations

from decimal import Decimal

from app.pricing.schemas import (
    DealScoringInput,
    FakeDiscountAnalysis,
    FakeDiscountFlag,
    PriceAggregation,
)
from app.pricing.scoring import score_business_priority, score_deal, score_deal_quality


def make_aggregation(**overrides) -> PriceAggregation:
    data = {
        "current_price": Decimal("70.00"),
        "avg_30d": Decimal("100.00"),
        "avg_90d": Decimal("95.00"),
        "min_90d": Decimal("70.00"),
        "max_90d": Decimal("110.00"),
        "all_time_min": Decimal("70.00"),
        "all_time_max": Decimal("120.00"),
        "days_at_current_price": 2,
        "observation_count_30d": 20,
        "observation_count_90d": 50,
        "observation_count_all_time": 120,
    }
    data.update(overrides)
    return PriceAggregation(**data)


def make_input(**overrides) -> DealScoringInput:
    data = {
        "current_price": Decimal("70.00"),
        "claimed_old_price": Decimal("100.00"),
        "aggregation": make_aggregation(),
        "fake_discount_analysis": FakeDiscountAnalysis(is_fake_discount=False, flags=[]),
        "is_featured": False,
        "merchant_priority": 5,
        "source_priority": 10,
        "category_priority": 0,
    }
    data.update(overrides)
    return DealScoringInput(**data)


def test_quality_score_promotable_for_real_user_value() -> None:
    quality = score_deal_quality(make_input())

    assert quality.promotable is True
    assert quality.score >= 60
    assert "at_all_time_low" in quality.reasons


def test_quality_score_zero_for_fake_discount() -> None:
    input_data = make_input(
        fake_discount_analysis=FakeDiscountAnalysis(
            is_fake_discount=True,
            flags=[FakeDiscountFlag(code="claimed_old_price_never_observed", message="bad", blocking=True)],
        )
    )

    quality = score_deal_quality(input_data)

    assert quality.promotable is False
    assert quality.score == 0
    assert "fake_discount_detected" in quality.reasons


def test_business_score_blocked_when_quality_is_bad() -> None:
    business = score_business_priority(
        make_input(is_featured=True, merchant_priority=30, source_priority=25, category_priority=25),
        promotable=False,
    )

    assert business.score == 0
    assert business.reasons == ["blocked_by_quality"]


def test_score_deal_separates_quality_and_business() -> None:
    scored = score_deal(
        make_input(
            is_featured=True,
            merchant_priority=20,
            source_priority=15,
            category_priority=10,
        )
    )

    assert scored.quality.promotable is True
    assert scored.quality.score > 0
    assert scored.business.score == 45
