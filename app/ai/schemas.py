from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass(slots=True)
class StructuredDealCopyInput:
    deal_id: str
    product_name: str
    merchant_name: str | None
    brand: str | None
    category: str | None
    current_price: Decimal
    previous_price: Decimal | None
    currency: str
    savings_amount: Decimal | None
    savings_percent: Decimal | None
    quality_score: int
    business_score: int
    promotable: bool
    fake_discount: bool
    days_at_current_price: int
    avg_30d: Decimal | None
    avg_90d: Decimal | None
    min_90d: Decimal | None
    all_time_min: Decimal | None
    variant_summary: str | None = None


@dataclass(slots=True)
class DealCopyOutput:
    title: str
    summary: str
    verdict: str
    tags: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ValidatedDealCopy:
    output: DealCopyOutput
    warnings: list[str] = field(default_factory=list)
