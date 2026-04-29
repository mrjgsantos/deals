from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from app.pricing.schemas import FakeDiscountAnalysis, FakeDiscountFlag, PriceAggregation


MAX_SALE_DURATION_DAYS = 21
HISTORICAL_AVERAGE_TOLERANCE = Decimal("1.02")
DISCOUNT_MATH_TOLERANCE = Decimal("0.02")


def analyze_fake_discount(
    *,
    current_price: Decimal,
    claimed_old_price: Decimal | None,
    claimed_discount_percent: Decimal | None,
    aggregation: PriceAggregation,
) -> FakeDiscountAnalysis:
    flags: list[FakeDiscountFlag] = []

    if claimed_old_price is not None:
        historically_observed_max = _historically_observed_max(aggregation)
        # Only flag if we have a historical max to compare against AND the
        # current price is not independently confirmed as a good deal by our
        # own data. If current_price <= avg_90d we already have evidence the
        # price is genuinely low, so a merchant's unverified reference price
        # should not block the deal.
        price_confirmed_low = (
            aggregation.avg_90d is not None and current_price <= aggregation.avg_90d
        )
        if (
            historically_observed_max is not None
            and claimed_old_price > historically_observed_max
            and not price_confirmed_low
        ):
            flags.append(
                FakeDiscountFlag(
                    code="claimed_old_price_never_observed",
                    message="Claimed old price is above observed historical prices",
                    blocking=True,
                )
            )

    if aggregation.days_at_current_price > MAX_SALE_DURATION_DAYS:
        flags.append(
            FakeDiscountFlag(
                code="current_sale_price_active_too_long",
                message="Current sale price has been active too long",
                blocking=True,
            )
        )

    if aggregation.avg_90d is not None and current_price > aggregation.avg_90d * HISTORICAL_AVERAGE_TOLERANCE:
        flags.append(
            FakeDiscountFlag(
                code="current_price_above_historical_average",
                message="Current price is above the 90-day average",
                blocking=True,
            )
        )

    if (
        claimed_old_price is not None
        and claimed_discount_percent is not None
        and claimed_old_price > 0
    ):
        computed_discount = ((claimed_old_price - current_price) / claimed_old_price) * Decimal("100")
        computed_discount = computed_discount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if abs(computed_discount - claimed_discount_percent) > DISCOUNT_MATH_TOLERANCE:
            flags.append(
                FakeDiscountFlag(
                    code="claimed_discount_math_inconsistent",
                    message="Claimed discount percent does not match price math",
                    blocking=True,
                )
            )

    return FakeDiscountAnalysis(
        is_fake_discount=any(flag.blocking for flag in flags),
        flags=flags,
    )


def _historically_observed_max(aggregation: PriceAggregation) -> Decimal | None:
    candidates = [
        aggregation.max_90d,
        aggregation.all_time_max,
    ]
    observed_candidates = [candidate for candidate in candidates if candidate is not None]
    if not observed_candidates:
        return None
    return max(observed_candidates)
