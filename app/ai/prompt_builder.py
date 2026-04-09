from __future__ import annotations

import json

from app.ai.schemas import StructuredDealCopyInput


SYSTEM_PROMPT = """You write concise editorial deal copy.
Return JSON only with keys: title, summary, verdict, tags.
Do not invent facts.
Do not mention unprovided shipping, stock, warranty, scarcity, exclusivity, or time limits.
Do not decide publish or reject.
Do not use marketing fluff.
Tags must be a JSON array of 1 to 5 short lowercase tags."""


def build_copy_prompt(data: StructuredDealCopyInput) -> str:
    structured_payload = {
        "deal_id": data.deal_id,
        "product_name": data.product_name,
        "merchant_name": data.merchant_name,
        "brand": data.brand,
        "category": data.category,
        "current_price": str(data.current_price),
        "previous_price": str(data.previous_price) if data.previous_price is not None else None,
        "currency": data.currency,
        "savings_amount": str(data.savings_amount) if data.savings_amount is not None else None,
        "savings_percent": str(data.savings_percent) if data.savings_percent is not None else None,
        "quality_score": data.quality_score,
        "business_score": data.business_score,
        "promotable": data.promotable,
        "fake_discount": data.fake_discount,
        "days_at_current_price": data.days_at_current_price,
        "avg_30d": str(data.avg_30d) if data.avg_30d is not None else None,
        "avg_90d": str(data.avg_90d) if data.avg_90d is not None else None,
        "min_90d": str(data.min_90d) if data.min_90d is not None else None,
        "all_time_min": str(data.all_time_min) if data.all_time_min is not None else None,
        "variant_summary": data.variant_summary,
    }

    instructions = {
        "title": "One factual line. Mention product and current price. Max 90 chars.",
        "summary": "Two factual sentences max. Mention price context only if supported by data.",
        "verdict": "One of: strong_value, fair_price, weak_value, not_supported.",
        "tags": "1 to 5 lowercase tags from product/category/value context only.",
    }

    return (
        f"{SYSTEM_PROMPT}\n\n"
        f"INPUT_JSON:\n{json.dumps(structured_payload, indent=2, sort_keys=True)}\n\n"
        f"OUTPUT_RULES:\n{json.dumps(instructions, indent=2, sort_keys=True)}"
    )
