from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal


@dataclass(slots=True)
class PricePoint:
    observed_at: datetime
    sale_price: Decimal
    list_price: Decimal | None = None
    total_price: Decimal | None = None


@dataclass(slots=True)
class PriceAggregation:
    current_price: Decimal
    avg_30d: Decimal | None
    avg_90d: Decimal | None
    min_90d: Decimal | None
    max_90d: Decimal | None
    all_time_min: Decimal | None
    all_time_max: Decimal | None
    days_at_current_price: int
    observation_count_30d: int
    observation_count_90d: int
    observation_count_all_time: int


@dataclass(slots=True)
class FakeDiscountFlag:
    code: str
    message: str
    blocking: bool


@dataclass(slots=True)
class FakeDiscountAnalysis:
    is_fake_discount: bool
    flags: list[FakeDiscountFlag] = field(default_factory=list)


@dataclass(slots=True)
class DealScoringInput:
    current_price: Decimal
    claimed_old_price: Decimal | None
    aggregation: PriceAggregation
    fake_discount_analysis: FakeDiscountAnalysis
    title: str | None = None
    source_category: str | None = None
    is_featured: bool = False
    merchant_priority: int = 0
    source_priority: int = 0
    category_priority: int = 0
    source_link_quality: str | None = None


@dataclass(slots=True)
class DealQualityScore:
    score: int
    promotable: bool
    confidence_level: str = "high"
    reasons: list[str] = field(default_factory=list)


@dataclass(slots=True)
class BusinessPriorityScore:
    score: int
    reasons: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ScoredDeal:
    quality: DealQualityScore
    business: BusinessPriorityScore
