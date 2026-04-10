from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from urllib.parse import urlparse

from app.pricing.schemas import (
    BusinessPriorityScore,
    DealQualityScore,
    DealScoringInput,
    ScoredDeal,
)


def score_deal(input_data: DealScoringInput) -> ScoredDeal:
    quality = score_deal_quality(input_data)
    business = score_business_priority(input_data, promotable=quality.promotable)
    return ScoredDeal(quality=quality, business=business)


def score_deal_quality(input_data: DealScoringInput) -> DealQualityScore:
    reasons: list[str] = []

    if input_data.fake_discount_analysis.is_fake_discount:
        reasons.append("fake_discount_detected")
        return DealQualityScore(score=0, promotable=False, reasons=reasons)

    score = 50
    baseline = _best_baseline(input_data)
    savings_percent: Decimal | None = None

    if baseline is not None and baseline > 0:
        savings_percent = ((baseline - input_data.current_price) / baseline) * Decimal("100")
        savings_percent = savings_percent.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if savings_percent >= Decimal("30"):
            score += 25
            reasons.append("strong_discount_vs_baseline")
        elif savings_percent >= Decimal("15"):
            score += 15
            reasons.append("meaningful_discount_vs_baseline")
        elif savings_percent <= Decimal("0"):
            score -= 30
            reasons.append("no_user_savings_vs_baseline")
    else:
        score -= 10
        reasons.append("limited_price_history")

    if input_data.aggregation.all_time_min is not None:
        if input_data.current_price <= input_data.aggregation.all_time_min:
            score += 20
            reasons.append("at_all_time_low")

    if input_data.aggregation.days_at_current_price <= 3:
        score += 10
        reasons.append("fresh_price_drop")
    elif input_data.aggregation.days_at_current_price > 14:
        score -= 20
        reasons.append("stale_price")

    history_support_adjustment, history_support_reasons = _history_support_adjustment(input_data)
    score += history_support_adjustment
    reasons.extend(history_support_reasons)

    volatility_adjustment, volatility_reasons = _history_volatility_adjustment(input_data)
    score += volatility_adjustment
    reasons.extend(volatility_reasons)

    discount_support_adjustment, discount_support_reasons = _discount_support_adjustment(input_data, savings_percent)
    score += discount_support_adjustment
    reasons.extend(discount_support_reasons)

    score = max(0, min(100, score))
    promotable = score >= 60 and "fake_discount_detected" not in reasons and "no_user_savings_vs_baseline" not in reasons

    return DealQualityScore(
        score=score,
        promotable=promotable,
        reasons=reasons,
    )


def score_business_priority(input_data: DealScoringInput, *, promotable: bool) -> BusinessPriorityScore:
    reasons: list[str] = []
    if not promotable:
        return BusinessPriorityScore(score=0, reasons=["blocked_by_quality"])

    score = 0

    if input_data.merchant_priority:
        score += max(0, min(30, input_data.merchant_priority))
        reasons.append("merchant_priority")

    if input_data.source_priority:
        score += max(0, min(25, input_data.source_priority))
        reasons.append("source_priority")

    if input_data.category_priority:
        score += max(0, min(25, input_data.category_priority))
        reasons.append("category_priority")

    if input_data.source_link_quality == "indirect_redirect":
        score -= 10
        reasons.append("indirect_source_link")

    return BusinessPriorityScore(
        score=max(0, min(100, score)),
        reasons=reasons or ["placeholder_default"],
    )


def classify_source_link_quality(url: str | None) -> str | None:
    if not url:
        return None
    try:
        parsed = urlparse(url)
    except ValueError:
        return None

    host = (parsed.netloc or "").casefold()
    path = (parsed.path or "").casefold()
    if "google." in host and ("/shopping/" in path or path.startswith("/url") or path.startswith("/aclk")):
        return "indirect_redirect"
    return "direct"


def _best_baseline(input_data: DealScoringInput) -> Decimal | None:
    candidates = (
        input_data.claimed_old_price,
        input_data.aggregation.avg_30d,
        input_data.aggregation.avg_90d,
    )
    for candidate in candidates:
        if candidate is not None and candidate > 0:
            return candidate
    return None


def _history_support_adjustment(input_data: DealScoringInput) -> tuple[int, list[str]]:
    aggregation = input_data.aggregation
    if (
        aggregation.observation_count_30d >= 10
        and aggregation.observation_count_90d >= 30
        and aggregation.observation_count_all_time >= 90
    ):
        return 10, ["strong_history_support"]
    if (
        aggregation.observation_count_30d >= 5
        and aggregation.observation_count_90d >= 15
        and aggregation.observation_count_all_time >= 45
    ):
        return 5, ["adequate_history_support"]
    return 0, []


def _history_volatility_adjustment(input_data: DealScoringInput) -> tuple[int, list[str]]:
    aggregation = input_data.aggregation
    if (
        aggregation.observation_count_90d < 10
        or aggregation.avg_90d is None
        or aggregation.avg_90d <= 0
        or aggregation.min_90d is None
        or aggregation.max_90d is None
    ):
        return 0, []

    range_percent = ((aggregation.max_90d - aggregation.min_90d) / aggregation.avg_90d) * Decimal("100")
    if range_percent <= Decimal("15"):
        return 5, ["stable_price_history"]
    if range_percent >= Decimal("60"):
        return -25, ["volatile_price_history"]
    return 0, []


def _discount_support_adjustment(
    input_data: DealScoringInput,
    savings_percent: Decimal | None,
) -> tuple[int, list[str]]:
    if savings_percent is None or savings_percent < Decimal("15"):
        return 0, []

    aggregation = input_data.aggregation
    if aggregation.observation_count_90d < 5 or aggregation.observation_count_all_time < 10:
        return -25, ["weak_discount_support"]
    if aggregation.observation_count_90d < 15 or aggregation.observation_count_all_time < 30:
        return -10, ["limited_discount_support"]
    return 0, []
