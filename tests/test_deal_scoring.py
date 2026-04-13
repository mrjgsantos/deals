from __future__ import annotations

from decimal import Decimal

from app.pricing.schemas import (
    DealScoringInput,
    FakeDiscountAnalysis,
    FakeDiscountFlag,
    PriceAggregation,
)
from app.pricing.scoring import classify_source_link_quality, score_business_priority, score_deal, score_deal_quality


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
        "title": "Cordless vacuum cleaner",
        "source_category": "Home",
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


def test_strong_history_support_beats_weak_history_support() -> None:
    strong_quality = score_deal_quality(
        make_input(
            aggregation=make_aggregation(
                observation_count_30d=20,
                observation_count_90d=50,
                observation_count_all_time=120,
            )
        )
    )
    weak_quality = score_deal_quality(
        make_input(
            aggregation=make_aggregation(
                observation_count_30d=2,
                observation_count_90d=4,
                observation_count_all_time=8,
            )
        )
    )

    assert strong_quality.score > weak_quality.score
    assert "strong_history_support" in strong_quality.reasons
    assert "weak_demand_signal" in weak_quality.reasons


def test_shallow_history_discount_gets_penalized() -> None:
    quality = score_deal_quality(
        make_input(
            aggregation=make_aggregation(
                observation_count_30d=1,
                observation_count_90d=3,
                observation_count_all_time=6,
            )
        )
    )

    assert "weak_demand_signal" in quality.reasons
    assert quality.score <= 80


def test_stable_history_scores_better_than_noisy_history() -> None:
    stable_quality = score_deal_quality(
        make_input(
            current_price=Decimal("82.00"),
            claimed_old_price=Decimal("100.00"),
            title="Cordless vacuum cleaner",
            source_category="Home",
            aggregation=make_aggregation(
                current_price=Decimal("82.00"),
                avg_30d=Decimal("100.00"),
                avg_90d=Decimal("100.00"),
                min_90d=Decimal("95.00"),
                max_90d=Decimal("105.00"),
                all_time_min=Decimal("70.00"),
                days_at_current_price=5,
                observation_count_30d=20,
                observation_count_90d=50,
                observation_count_all_time=120,
            )
        )
    )
    noisy_quality = score_deal_quality(
        make_input(
            current_price=Decimal("82.00"),
            claimed_old_price=Decimal("100.00"),
            title="Cordless vacuum cleaner",
            source_category="Home",
            aggregation=make_aggregation(
                current_price=Decimal("82.00"),
                avg_30d=Decimal("100.00"),
                avg_90d=Decimal("100.00"),
                min_90d=Decimal("50.00"),
                max_90d=Decimal("150.00"),
                all_time_min=Decimal("70.00"),
                days_at_current_price=5,
                observation_count_30d=20,
                observation_count_90d=50,
                observation_count_all_time=120,
            )
        )
    )

    assert stable_quality.score > noisy_quality.score
    assert "stable_price_history" in stable_quality.reasons
    assert "volatile_price_history" in noisy_quality.reasons


def test_bad_quality_input_cannot_reach_unrealistically_strong_score() -> None:
    quality = score_deal_quality(
        make_input(
            claimed_old_price=Decimal("140.00"),
            aggregation=make_aggregation(
                observation_count_30d=1,
                observation_count_90d=2,
                observation_count_all_time=4,
                avg_90d=Decimal("140.00"),
                min_90d=Decimal("70.00"),
                max_90d=Decimal("140.00"),
            ),
        )
    )

    assert quality.score < 90
    assert "weak_demand_signal" in quality.reasons


def test_historically_strong_low_price_scores_better_than_non_low_supported_price() -> None:
    strong_low_quality = score_deal_quality(
        make_input(
            current_price=Decimal("70.00"),
            claimed_old_price=Decimal("95.00"),
            aggregation=make_aggregation(
                current_price=Decimal("70.00"),
                avg_30d=Decimal("95.00"),
                avg_90d=Decimal("96.00"),
                min_90d=Decimal("70.00"),
                max_90d=Decimal("110.00"),
                all_time_min=Decimal("70.00"),
                observation_count_30d=12,
                observation_count_90d=30,
                observation_count_all_time=60,
            ),
        )
    )
    non_low_quality = score_deal_quality(
        make_input(
            current_price=Decimal("80.00"),
            claimed_old_price=Decimal("95.00"),
            aggregation=make_aggregation(
                current_price=Decimal("80.00"),
                avg_30d=Decimal("95.00"),
                avg_90d=Decimal("96.00"),
                min_90d=Decimal("70.00"),
                max_90d=Decimal("110.00"),
                all_time_min=Decimal("70.00"),
                observation_count_30d=12,
                observation_count_90d=30,
                observation_count_all_time=60,
            ),
        )
    )

    assert strong_low_quality.score > non_low_quality.score
    assert "at_all_time_low" in strong_low_quality.reasons


def test_noisy_history_discount_does_not_overstate_confidence() -> None:
    quality = score_deal_quality(
        make_input(
            current_price=Decimal("70.00"),
            claimed_old_price=Decimal("100.00"),
            title="Cordless vacuum cleaner",
            source_category="Home",
            aggregation=make_aggregation(
                current_price=Decimal("70.00"),
                avg_30d=Decimal("100.00"),
                avg_90d=Decimal("100.00"),
                min_90d=Decimal("45.00"),
                max_90d=Decimal("155.00"),
                all_time_min=Decimal("65.00"),
                days_at_current_price=5,
                observation_count_30d=18,
                observation_count_90d=45,
                observation_count_all_time=90,
            ),
        )
    )

    assert "volatile_price_history" in quality.reasons
    assert quality.score <= 90


def test_business_score_penalizes_indirect_source_link() -> None:
    business = score_business_priority(
        make_input(
            merchant_priority=20,
            source_priority=15,
            category_priority=10,
            source_link_quality="indirect_redirect",
        ),
        promotable=True,
    )

    assert business.score == 35
    assert "indirect_source_link" in business.reasons


def test_classify_source_link_quality_detects_google_redirects() -> None:
    assert classify_source_link_quality("https://www.google.com/shopping/product/123") == "indirect_redirect"
    assert classify_source_link_quality("https://www.amazon.com/dp/B0TEST") == "direct"


def test_quality_score_rejects_low_price_non_high_demand_item() -> None:
    quality = score_deal_quality(
        make_input(
            current_price=Decimal("12.99"),
            claimed_old_price=Decimal("19.99"),
            title="Bed sheets set",
            source_category="Bedding",
            aggregation=make_aggregation(
                current_price=Decimal("12.99"),
                avg_30d=Decimal("19.99"),
                avg_90d=Decimal("20.99"),
                min_90d=Decimal("12.99"),
                max_90d=Decimal("24.99"),
            ),
        )
    )

    assert quality.promotable is False
    assert quality.score == 0
    assert "low_price_low_demand" in quality.reasons


def test_quality_score_allows_low_price_high_demand_electronics() -> None:
    quality = score_deal_quality(
        make_input(
            current_price=Decimal("12.99"),
            claimed_old_price=Decimal("19.99"),
            title="Anker USB-C charger",
            source_category="Electronics",
            aggregation=make_aggregation(
                current_price=Decimal("12.99"),
                avg_30d=Decimal("19.99"),
                avg_90d=Decimal("20.99"),
                min_90d=Decimal("12.99"),
                max_90d=Decimal("24.99"),
                observation_count_30d=10,
                observation_count_90d=24,
                observation_count_all_time=40,
            ),
        )
    )

    assert quality.promotable is True
    assert quality.score >= 70
    assert "high_demand_category" in quality.reasons


def test_quality_score_rejects_low_signal_commodity() -> None:
    quality = score_deal_quality(
        make_input(
            title="Relec extra fuerte repelente de insectos",
            source_category="Pest Control",
        )
    )

    assert quality.promotable is False
    assert quality.score == 0
    assert "low_signal_commodity" in quality.reasons


def test_quality_score_rejects_weak_discount_vs_historical_average() -> None:
    quality = score_deal_quality(
        make_input(
            current_price=Decimal("90.00"),
            claimed_old_price=Decimal("110.00"),
            aggregation=make_aggregation(
                current_price=Decimal("90.00"),
                avg_30d=Decimal("100.00"),
                avg_90d=Decimal("102.00"),
                min_90d=Decimal("85.00"),
                max_90d=Decimal("110.00"),
            ),
        )
    )

    assert quality.promotable is False
    assert quality.score == 0
    assert "weak_discount_vs_historical_average" in quality.reasons


def test_quality_score_rejects_weak_demand_signal() -> None:
    quality = score_deal_quality(
        make_input(
            aggregation=make_aggregation(
                observation_count_30d=1,
                observation_count_90d=4,
                observation_count_all_time=12,
            )
        )
    )

    assert quality.promotable is False
    assert quality.score == 0
    assert "weak_demand_signal" in quality.reasons


def test_quality_score_boosts_recognized_brands() -> None:
    generic = score_deal_quality(
        make_input(
            title="Wireless headphones",
            source_category="Audio",
            current_price=Decimal("82.00"),
            claimed_old_price=Decimal("100.00"),
            aggregation=make_aggregation(
                current_price=Decimal("82.00"),
                avg_30d=Decimal("100.00"),
                avg_90d=Decimal("100.00"),
                min_90d=Decimal("80.00"),
                max_90d=Decimal("110.00"),
                all_time_min=Decimal("75.00"),
                days_at_current_price=5,
                observation_count_30d=12,
                observation_count_90d=30,
                observation_count_all_time=60,
            ),
        )
    )
    branded = score_deal_quality(
        make_input(
            title="Sony WH-1000XM5 headphones",
            source_category="Audio",
            current_price=Decimal("82.00"),
            claimed_old_price=Decimal("100.00"),
            aggregation=make_aggregation(
                current_price=Decimal("82.00"),
                avg_30d=Decimal("100.00"),
                avg_90d=Decimal("100.00"),
                min_90d=Decimal("80.00"),
                max_90d=Decimal("110.00"),
                all_time_min=Decimal("75.00"),
                days_at_current_price=5,
                observation_count_30d=12,
                observation_count_90d=30,
                observation_count_all_time=60,
            ),
        )
    )

    assert branded.score > generic.score
    assert "recognized_brand" in branded.reasons
