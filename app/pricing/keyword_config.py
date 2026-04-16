"""Load scoring keyword lists from the database, falling back to hard-coded defaults."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ScoringKeyword
from app.pricing.schemas import ScoringKeywordConfig
from app.pricing.scoring import (
    HIGH_DEMAND_KEYWORDS,
    HIGH_RECOGNITION_BRANDS,
    LOW_SIGNAL_COMMODITY_CATEGORIES,
    LOW_SIGNAL_COMMODITY_KEYWORDS,
)

_LIST_HIGH_DEMAND = "high_demand"
_LIST_RECOGNIZED_BRAND = "recognized_brand"
_LIST_LOW_SIGNAL_KEYWORD = "low_signal_keyword"
_LIST_LOW_SIGNAL_CATEGORY = "low_signal_category"


def load_keyword_config(db: Session) -> ScoringKeywordConfig:
    """Query enabled keywords from the DB and return a ScoringKeywordConfig.

    If a list is empty in the DB (e.g. not seeded yet), returns None for that
    field so scoring falls back to the hard-coded defaults.
    """
    rows = db.execute(
        select(ScoringKeyword.list_name, ScoringKeyword.keyword)
        .where(ScoringKeyword.enabled.is_(True))
        .order_by(ScoringKeyword.list_name, ScoringKeyword.keyword)
    ).all()

    buckets: dict[str, list[str]] = {
        _LIST_HIGH_DEMAND: [],
        _LIST_RECOGNIZED_BRAND: [],
        _LIST_LOW_SIGNAL_KEYWORD: [],
        _LIST_LOW_SIGNAL_CATEGORY: [],
    }
    for list_name, keyword in rows:
        if list_name in buckets:
            buckets[list_name].append(keyword)

    return ScoringKeywordConfig(
        high_demand_keywords=tuple(buckets[_LIST_HIGH_DEMAND]) or None,
        recognized_brands=tuple(buckets[_LIST_RECOGNIZED_BRAND]) or None,
        low_signal_keywords=tuple(buckets[_LIST_LOW_SIGNAL_KEYWORD]) or None,
        low_signal_categories=tuple(buckets[_LIST_LOW_SIGNAL_CATEGORY]) or None,
    )


def default_seed_rows() -> list[dict]:
    """Return insert-ready dicts for seeding the hard-coded defaults."""
    entries = []
    for kw in HIGH_DEMAND_KEYWORDS:
        entries.append({"list_name": _LIST_HIGH_DEMAND, "keyword": kw})
    for kw in HIGH_RECOGNITION_BRANDS:
        entries.append({"list_name": _LIST_RECOGNIZED_BRAND, "keyword": kw})
    for kw in LOW_SIGNAL_COMMODITY_KEYWORDS:
        entries.append({"list_name": _LIST_LOW_SIGNAL_KEYWORD, "keyword": kw})
    for kw in LOW_SIGNAL_COMMODITY_CATEGORIES:
        entries.append({"list_name": _LIST_LOW_SIGNAL_CATEGORY, "keyword": kw})
    return entries
