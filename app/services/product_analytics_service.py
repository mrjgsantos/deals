from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Iterable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Deal, UserEvent

EVENT_USER_SIGNUP = "user_signup"
EVENT_ONBOARDING_COMPLETED = "onboarding_completed"
EVENT_DEAL_IMPRESSION = "deal_impression"
EVENT_DEAL_CLICK = "deal_click"
EVENT_DEAL_SAVED = "deal_saved"
EVENT_DEAL_UNSAVED = "deal_unsaved"
EVENT_RECOMMENDED_DEAL_IMPRESSION = "recommended_deal_impression"
EVENT_RECOMMENDED_DEAL_CLICK = "recommended_deal_click"

TRACKED_EVENT_TYPES = {
    EVENT_USER_SIGNUP,
    EVENT_ONBOARDING_COMPLETED,
    EVENT_DEAL_IMPRESSION,
    EVENT_DEAL_CLICK,
    EVENT_DEAL_SAVED,
    EVENT_DEAL_UNSAVED,
    EVENT_RECOMMENDED_DEAL_IMPRESSION,
    EVENT_RECOMMENDED_DEAL_CLICK,
}

DEDUPED_DEAL_EVENT_TYPES = {
    EVENT_DEAL_IMPRESSION,
    EVENT_DEAL_CLICK,
    EVENT_DEAL_SAVED,
    EVENT_DEAL_UNSAVED,
    EVENT_RECOMMENDED_DEAL_IMPRESSION,
    EVENT_RECOMMENDED_DEAL_CLICK,
}
DEDUPED_USER_EVENT_TYPES = {
    EVENT_USER_SIGNUP,
    EVENT_ONBOARDING_COMPLETED,
}


@dataclass(slots=True)
class ProductAnalyticsDealPerformanceRecord:
    deal_id: UUID
    title: str
    category: str | None
    impression_count: int = 0
    click_count: int = 0
    save_count: int = 0
    unsave_count: int = 0
    recommended_impression_count: int = 0
    recommended_click_count: int = 0
    ctr: float = 0.0
    save_rate: float = 0.0
    recommended_ctr: float = 0.0


@dataclass(slots=True)
class ProductAnalyticsOverviewRecord:
    days: int
    user_signups: int = 0
    onboarding_completed: int = 0
    deal_impressions: int = 0
    deal_clicks: int = 0
    deal_saves: int = 0
    deal_unsaves: int = 0
    recommended_deal_impressions: int = 0
    recommended_deal_clicks: int = 0
    ctr: float = 0.0
    save_rate: float = 0.0
    recommendation_ctr: float = 0.0
    top_deals: list[ProductAnalyticsDealPerformanceRecord] = field(default_factory=list)


class ProductAnalyticsService:
    def record_event(
        self,
        db: Session,
        *,
        user_id: UUID,
        event_type: str,
        deal_id: UUID | None = None,
        occurred_at: datetime | None = None,
    ) -> bool:
        if event_type not in TRACKED_EVENT_TYPES:
            raise ValueError("unsupported_event_type")

        if self._event_already_recorded(
            db,
            user_id=user_id,
            event_type=event_type,
            deal_id=deal_id,
        ):
            return False

        event = UserEvent(
            user_id=user_id,
            event_type=event_type,
            deal_id=deal_id,
        )
        if occurred_at is not None:
            event.created_at = occurred_at.astimezone(UTC) if occurred_at.tzinfo else occurred_at.replace(tzinfo=UTC)
        db.add(event)
        db.flush()
        return True

    def record_impressions(
        self,
        db: Session,
        *,
        user_id: UUID,
        deal_ids: Iterable[UUID],
        recommended: bool = False,
    ) -> int:
        unique_ids: list[UUID] = []
        seen: set[UUID] = set()
        for deal_id in deal_ids:
            if deal_id in seen:
                continue
            unique_ids.append(deal_id)
            seen.add(deal_id)

        event_type = EVENT_RECOMMENDED_DEAL_IMPRESSION if recommended else EVENT_DEAL_IMPRESSION
        tracked = 0
        for deal_id in unique_ids:
            if self.record_event(db, user_id=user_id, event_type=event_type, deal_id=deal_id):
                tracked += 1
        return tracked

    def get_overview(
        self,
        db: Session,
        *,
        days: int = 30,
        limit: int = 10,
    ) -> ProductAnalyticsOverviewRecord:
        since = datetime.now(UTC) - timedelta(days=days)
        rows = db.execute(
            select(UserEvent.user_id, UserEvent.event_type, UserEvent.deal_id, Deal.title)
            .select_from(UserEvent)
            .join(Deal, Deal.id == UserEvent.deal_id, isouter=True)
            .where(UserEvent.created_at >= since)
        ).all()

        counts = {event_type: 0 for event_type in TRACKED_EVENT_TYPES}
        by_deal: dict[UUID, ProductAnalyticsDealPerformanceRecord] = {}
        seen_event_keys: set[tuple[UUID, str, UUID | None]] = set()

        for user_id, event_type, deal_id, title in rows:
            event_key = (user_id, event_type, deal_id)
            if event_key in seen_event_keys:
                continue
            seen_event_keys.add(event_key)
            counts[event_type] = counts.get(event_type, 0) + 1
            if deal_id is None:
                continue
            record = by_deal.setdefault(
                deal_id,
                ProductAnalyticsDealPerformanceRecord(
                    deal_id=deal_id,
                    title=title or "Unknown deal",
                    category=None,
                ),
            )
            if event_type == EVENT_DEAL_IMPRESSION:
                record.impression_count += 1
            elif event_type == EVENT_DEAL_CLICK:
                record.click_count += 1
            elif event_type == EVENT_DEAL_SAVED:
                record.save_count += 1
            elif event_type == EVENT_DEAL_UNSAVED:
                record.unsave_count += 1
            elif event_type == EVENT_RECOMMENDED_DEAL_IMPRESSION:
                record.recommended_impression_count += 1
            elif event_type == EVENT_RECOMMENDED_DEAL_CLICK:
                record.recommended_click_count += 1

        for record in by_deal.values():
            record.ctr = _safe_rate(record.click_count, record.impression_count)
            record.save_rate = _safe_rate(record.save_count, record.impression_count)
            record.recommended_ctr = _safe_rate(record.recommended_click_count, record.recommended_impression_count)

        top_deals = sorted(
            by_deal.values(),
            key=lambda item: (
                item.click_count + item.recommended_click_count,
                item.save_count,
                item.ctr,
                item.recommended_ctr,
                item.title,
            ),
            reverse=True,
        )[:limit]

        return ProductAnalyticsOverviewRecord(
            days=days,
            user_signups=counts[EVENT_USER_SIGNUP],
            onboarding_completed=counts[EVENT_ONBOARDING_COMPLETED],
            deal_impressions=counts[EVENT_DEAL_IMPRESSION],
            deal_clicks=counts[EVENT_DEAL_CLICK],
            deal_saves=counts[EVENT_DEAL_SAVED],
            deal_unsaves=counts[EVENT_DEAL_UNSAVED],
            recommended_deal_impressions=counts[EVENT_RECOMMENDED_DEAL_IMPRESSION],
            recommended_deal_clicks=counts[EVENT_RECOMMENDED_DEAL_CLICK],
            ctr=_safe_rate(counts[EVENT_DEAL_CLICK], counts[EVENT_DEAL_IMPRESSION]),
            save_rate=_safe_rate(counts[EVENT_DEAL_SAVED], counts[EVENT_DEAL_IMPRESSION]),
            recommendation_ctr=_safe_rate(
                counts[EVENT_RECOMMENDED_DEAL_CLICK],
                counts[EVENT_RECOMMENDED_DEAL_IMPRESSION],
            ),
            top_deals=top_deals,
        )

    def _event_already_recorded(
        self,
        db: Session,
        *,
        user_id: UUID,
        event_type: str,
        deal_id: UUID | None,
    ) -> bool:
        if not hasattr(db, "scalar"):
            return False
        if event_type in DEDUPED_DEAL_EVENT_TYPES and deal_id is not None:
            existing = db.scalar(
                select(UserEvent.id).where(
                    UserEvent.user_id == user_id,
                    UserEvent.event_type == event_type,
                    UserEvent.deal_id == deal_id,
                )
            )
            return existing is not None
        if event_type in DEDUPED_USER_EVENT_TYPES and deal_id is None:
            existing = db.scalar(
                select(UserEvent.id).where(
                    UserEvent.user_id == user_id,
                    UserEvent.event_type == event_type,
                    UserEvent.deal_id.is_(None),
                )
            )
            return existing is not None
        return False


def _safe_rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)
