from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import PriceObservation, ProductSourceRecord
from app.pricing.schemas import PriceAggregation, PricePoint


def aggregate_price_history(
    price_points: list[PricePoint],
    now: datetime | None = None,
) -> PriceAggregation:
    if not price_points:
        raise ValueError("price history is required")

    normalized_now = now or datetime.now(UTC)
    ordered_points = sorted(price_points, key=lambda point: point.observed_at)
    current_price = ordered_points[-1].sale_price

    points_30d = [
        point
        for point in ordered_points
        if normalized_now - timedelta(days=30) <= point.observed_at < normalized_now
    ]
    points_90d = [
        point
        for point in ordered_points
        if normalized_now - timedelta(days=90) <= point.observed_at < normalized_now
    ]

    return PriceAggregation(
        current_price=current_price,
        avg_30d=_average_price(points_30d),
        avg_90d=_average_price(points_90d),
        min_90d=_minimum_price(points_90d),
        max_90d=_maximum_price(points_90d),
        all_time_min=_minimum_price(ordered_points),
        all_time_max=_maximum_price(ordered_points),
        days_at_current_price=_days_at_current_price(ordered_points, current_price, normalized_now),
        observation_count_30d=len(points_30d),
        observation_count_90d=len(points_90d),
        observation_count_all_time=len(ordered_points),
    )


def build_daily_price_statistics(price_points: list[PricePoint]) -> dict[datetime.date, Decimal]:
    buckets: dict[datetime.date, list[Decimal]] = defaultdict(list)
    for point in price_points:
        buckets[point.observed_at.date()].append(point.sale_price)

    return {
        day: _quantize(sum(values) / Decimal(len(values)))
        for day, values in sorted(buckets.items())
    }


def aggregate_price_history_for_variant(
    db: Session,
    product_variant_id,
    now: datetime | None = None,
) -> PriceAggregation:
    stmt = (
        select(
            PriceObservation.observed_at,
            PriceObservation.sale_price,
            PriceObservation.list_price,
            PriceObservation.total_price,
        )
        .join(
            ProductSourceRecord,
            PriceObservation.product_source_record_id == ProductSourceRecord.id,
        )
        .where(
            ProductSourceRecord.product_variant_id == product_variant_id,
            PriceObservation.sale_price.is_not(None),
        )
        .order_by(PriceObservation.observed_at.asc())
    )
    rows = db.execute(stmt).all()
    price_points = [
        PricePoint(
            observed_at=row.observed_at,
            sale_price=row.sale_price,
            list_price=row.list_price,
            total_price=row.total_price,
        )
        for row in rows
    ]
    return aggregate_price_history(price_points, now=now)


def _average_price(points: list[PricePoint]) -> Decimal | None:
    if not points:
        return None
    total = sum(point.sale_price for point in points)
    return _quantize(total / Decimal(len(points)))


def _minimum_price(points: list[PricePoint]) -> Decimal | None:
    if not points:
        return None
    return min(point.sale_price for point in points)


def _maximum_price(points: list[PricePoint]) -> Decimal | None:
    if not points:
        return None
    return max(point.sale_price for point in points)


def _days_at_current_price(points: list[PricePoint], current_price: Decimal, now: datetime) -> int:
    matching_points = [point for point in points if point.sale_price == current_price]
    if not matching_points:
        return 0
    first_match = min(point.observed_at for point in matching_points)
    return max(1, (now.date() - first_match.date()).days + 1)


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
