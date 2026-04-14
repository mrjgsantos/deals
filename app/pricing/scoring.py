from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from urllib.parse import urlparse

from app.pricing.schemas import (
    BusinessPriorityScore,
    DealQualityScore,
    DealScoringInput,
    ScoredDeal,
)

HIGH_DEMAND_KEYWORDS = (
    "tech",
    "gaming",
    "audio",
    "electronics",
    "electronic",
    "electrónica",
    "electronica",
    "smart home",
    "smart-home",
    "monitor",
    "ssd",
    "laptop",
    "tablet",
    "iphone",
    "xiaomi",
    "logitech",
    "anker",
    "sony",
    "playstation",
    "xbox",
    "nintendo",
)

HIGH_RECOGNITION_BRANDS = (
    "apple",
    "samsung",
    "xiaomi",
    "sony",
    "logitech",
    "anker",
    "philips",
    "tp-link",
    "nintendo",
    "playstation",
    "xbox",
    "dyson",
    "lg",
)

LOW_SIGNAL_COMMODITY_KEYWORDS = (
    "bedsheet",
    "bed sheets",
    "sabanas",
    "sábanas",
    "sheet set",
    "basic t-shirt",
    "camiseta basica",
    "camiseta básica",
    "legging basico",
    "legging básico",
    "insecticida",
    "repelente de insectos",
    "rat poison",
    "raticida",
    "ratonera",
    "ratoneras",
    "mouse trap",
    "funda para tarjetas",
    "memory card case",
    "sd card case",
    "cable organizer",
    "organizador de cables",
    "screen protector",
)

LOW_SIGNAL_COMMODITY_CATEGORIES = (
    "bedding",
    "ropa basica",
    "basic apparel",
    "pest control",
    "vitamins",
    "supplements",
    "accessories",
    "low-value accessories",
)


def score_deal(input_data: DealScoringInput) -> ScoredDeal:
    quality = score_deal_quality(input_data)
    business = score_business_priority(input_data, promotable=quality.promotable)
    return ScoredDeal(quality=quality, business=business)


def score_deal_quality(input_data: DealScoringInput) -> DealQualityScore:
    reasons: list[str] = []
    normalized_text = _normalized_text(input_data)
    confidence = _observation_confidence_tier(input_data)

    if input_data.fake_discount_analysis.is_fake_discount:
        reasons.append("fake_discount_detected")
        return DealQualityScore(score=0, promotable=False, confidence_level=confidence, reasons=reasons)

    score = 50
    baseline = _best_baseline(input_data)
    historical_average = _historical_average_baseline(input_data)
    savings_percent: Decimal | None = None
    high_demand_category = _is_high_demand_category(normalized_text)
    recognized_brand = _has_recognized_brand(normalized_text)

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

    if historical_average is not None and historical_average > 0:
        historical_discount = ((historical_average - input_data.current_price) / historical_average) * Decimal("100")
        historical_discount = historical_discount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if historical_discount < Decimal("15"):
            reasons.append("weak_discount_vs_historical_average")
            if confidence == "high":
                # Hard kill only when historical data is reliable
                return DealQualityScore(score=0, promotable=False, confidence_level=confidence, reasons=reasons)
            else:
                # Sparse history: penalise but don't discard — the average may not be representative
                score -= 15

    if input_data.current_price < Decimal("15") and not high_demand_category:
        reasons.append("low_price_low_demand")
        return DealQualityScore(score=0, promotable=False, confidence_level=confidence, reasons=reasons)

    if _is_low_signal_commodity(normalized_text):
        reasons.append("low_signal_commodity")
        return DealQualityScore(score=0, promotable=False, confidence_level=confidence, reasons=reasons)

    # Graded confidence penalty — replaces the former hard weak_demand_signal disqualifier.
    # LOW  (obs_90d < 3):                   -20, sends deal to PENDING_REVIEW via auto-publish gate
    # MEDIUM (obs_90d 3-7 or all_time < 20): -10, auto-publish requires higher score threshold
    # HIGH:                                   no penalty
    if confidence == "low":
        score -= 20
        reasons.append("low_historical_confidence")
    elif confidence == "medium":
        score -= 10
        reasons.append("low_historical_confidence")

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

    category_boost, category_reasons = _quality_category_adjustment(
        high_demand_category=high_demand_category,
        recognized_brand=recognized_brand,
    )
    score += category_boost
    reasons.extend(category_reasons)

    score = max(0, min(100, score))
    promotable = score >= 60 and "fake_discount_detected" not in reasons and "no_user_savings_vs_baseline" not in reasons

    return DealQualityScore(
        score=score,
        promotable=promotable,
        confidence_level=confidence,
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


def _historical_average_baseline(input_data: DealScoringInput) -> Decimal | None:
    for candidate in (input_data.aggregation.avg_30d, input_data.aggregation.avg_90d):
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


def _normalized_text(input_data: DealScoringInput) -> str:
    parts = [input_data.title or "", input_data.source_category or ""]
    return " ".join(part.strip().casefold() for part in parts if part and part.strip())


def _is_high_demand_category(normalized_text: str) -> bool:
    return any(keyword in normalized_text for keyword in HIGH_DEMAND_KEYWORDS)


def _has_recognized_brand(normalized_text: str) -> bool:
    return any(keyword in normalized_text for keyword in HIGH_RECOGNITION_BRANDS)


def _is_low_signal_commodity(normalized_text: str) -> bool:
    return any(keyword in normalized_text for keyword in LOW_SIGNAL_COMMODITY_KEYWORDS) or any(
        keyword in normalized_text for keyword in LOW_SIGNAL_COMMODITY_CATEGORIES
    )


def _observation_confidence_tier(input_data: DealScoringInput) -> str:
    """Return 'high', 'medium', or 'low' based on local price-observation depth."""
    aggregation = input_data.aggregation
    if aggregation.observation_count_90d >= 8 and aggregation.observation_count_all_time >= 20:
        return "high"
    if aggregation.observation_count_90d >= 3:
        return "medium"
    return "low"


def _quality_category_adjustment(*, high_demand_category: bool, recognized_brand: bool) -> tuple[int, list[str]]:
    adjustment = 0
    reasons: list[str] = []
    if high_demand_category:
        adjustment += 8
        reasons.append("high_demand_category")
    if recognized_brand:
        adjustment += 7
        reasons.append("recognized_brand")
    return adjustment, reasons
