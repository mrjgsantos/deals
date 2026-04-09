from __future__ import annotations

import re
from decimal import Decimal, ROUND_HALF_UP

from app.ai.schemas import DealCopyOutput, StructuredDealCopyInput, ValidatedDealCopy


SUPPORTED_VERDICTS = {"strong_value", "fair_price", "weak_value", "not_supported"}
UNSUPPORTED_CLAIM_PATTERNS = [
    re.compile(r"\b(best deal|must-buy|unbeatable|insane deal|guaranteed|free shipping|lowest ever)\b", re.I),
    re.compile(r"\b(limited time|won't last|sell out|hurry|exclusive)\b", re.I),
]
TAG_RE = re.compile(r"^[a-z0-9-]{2,24}$")
PERCENT_RE = re.compile(r"(\d+(?:\.\d+)?)%")


def validate_copy_output(output: DealCopyOutput, input_data: StructuredDealCopyInput) -> ValidatedDealCopy:
    warnings: list[str] = []

    if not output.title or len(output.title) > 90:
        raise ValueError("invalid title length")
    if not output.summary or len(output.summary) > 240:
        raise ValueError("invalid summary length")
    if output.verdict not in SUPPORTED_VERDICTS:
        raise ValueError("unsupported verdict")
    if not 1 <= len(output.tags) <= 5:
        raise ValueError("invalid tag count")

    for tag in output.tags:
        if not TAG_RE.fullmatch(tag):
            raise ValueError("invalid tag format")

    combined_text = " ".join([output.title, output.summary, output.verdict, " ".join(output.tags)])
    lowered_text = combined_text.casefold()

    for pattern in UNSUPPORTED_CLAIM_PATTERNS:
        if pattern.search(combined_text):
            raise ValueError("unsupported claim detected")

    if "all-time low" in lowered_text and (
        input_data.all_time_min is None or input_data.current_price > input_data.all_time_min
    ):
        raise ValueError("unsupported all-time-low claim")

    if "30-day average" in lowered_text and input_data.avg_30d is None:
        raise ValueError("unsupported 30-day-average claim")

    if "90-day average" in lowered_text and input_data.avg_90d is None:
        raise ValueError("unsupported 90-day-average claim")

    if "fake" in lowered_text or "publish" in lowered_text or "reject" in lowered_text:
        raise ValueError("copy output contains workflow decision language")

    if input_data.fake_discount and output.verdict != "not_supported":
        raise ValueError("fake discount copy must use not_supported verdict")

    if not input_data.promotable and output.verdict == "strong_value":
        raise ValueError("non-promotable deal cannot be labeled strong_value")

    percent_matches = PERCENT_RE.findall(combined_text)
    if percent_matches:
        expected = _expected_discount_percent(input_data)
        if expected is None:
            raise ValueError("percentage claim without supporting structured discount")
        for match in percent_matches:
            claimed = Decimal(match).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if abs(claimed - expected) > Decimal("1.00"):
                raise ValueError("percentage claim inconsistent with structured data")

    if input_data.merchant_name and input_data.merchant_name.casefold() not in lowered_text:
        warnings.append("merchant_name_not_mentioned")

    return ValidatedDealCopy(output=output, warnings=warnings)


def _expected_discount_percent(input_data: StructuredDealCopyInput) -> Decimal | None:
    if input_data.savings_percent is not None:
        return input_data.savings_percent.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if input_data.previous_price is None or input_data.previous_price <= 0:
        return None
    expected = ((input_data.previous_price - input_data.current_price) / input_data.previous_price) * Decimal("100")
    return expected.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
