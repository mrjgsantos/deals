from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

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

    return BusinessPriorityScore(
        score=max(0, min(100, score)),
        reasons=reasons or ["placeholder_default"],
    )


def _best_baseline(input_data: DealScoringInput) -> Decimal | None:
    candidates = [
        input_data.claimed_old_price,
        input_data.aggregation.avg_30d,
        input_data.aggregation.avg_90d,
    ]
    valid_candidates = [candidate for candidate in candidates if candidate is not None and candidate > 0]
    if not valid_candidates:
        return None
    return max(valid_candidates)
