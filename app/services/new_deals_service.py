from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.enums import DealStatus
from app.db.models import User, UserEvent
from app.services.deal_service import DealQueryService, DealRecord
from app.services.product_analytics_service import (
    EVENT_DEAL_CLICK,
    EVENT_DEAL_IMPRESSION,
    EVENT_RECOMMENDED_DEAL_CLICK,
    EVENT_RECOMMENDED_DEAL_IMPRESSION,
)
from app.services.personalization import PersonalizationService, infer_preference_categories_for_deal
from app.services.saved_deals_service import SavedDealsService

NEW_DEALS_FALLBACK_LOOKBACK = timedelta(days=14)


@dataclass(slots=True)
class NewDealsResult:
    last_seen_at: datetime | None
    new_count: int
    fallback_used: bool
    deals: list[DealRecord]


class NewDealsService:
    def __init__(self) -> None:
        self.deal_query_service = DealQueryService()
        self.saved_deals_service = SavedDealsService()
        self.personalization_service = PersonalizationService()

    def get_new_deals(
        self,
        db: Session,
        *,
        user: User,
        limit: int = 12,
        now: datetime | None = None,
    ) -> NewDealsResult:
        current_time = now or datetime.now(UTC)
        saved_deals = self.saved_deals_service.list_saved_deals(db, user=user)
        saved_deal_ids = {item.deal.id for item in saved_deals}
        interacted_deal_ids = self._interacted_deal_ids(db, user=user)

        seed_categories: set[str] = set()
        for item in saved_deals:
            seed_categories.update(infer_preference_categories_for_deal(item.deal))

        profile = self.personalization_service.load_profile(db, user=user, seed_categories=seed_categories)
        published_deals = [
            deal
            for deal in self.deal_query_service.list_deals(db)
            if deal.status in {DealStatus.APPROVED.value, DealStatus.PUBLISHED.value}
            if deal.published_at is not None
            if deal.id not in saved_deal_ids
            if deal.id not in interacted_deal_ids
        ]

        last_seen_at = self._normalize_last_seen(user.last_seen_deals_at)
        if last_seen_at is None:
            ranked = self._rank_fallback(published_deals, profile=profile, now=current_time)
            return NewDealsResult(
                last_seen_at=None,
                new_count=0,
                fallback_used=True,
                deals=ranked[:limit],
            )

        new_deals = [
            deal
            for deal in published_deals
            if self.personalization_service.freshness_datetime(deal) > last_seen_at
        ]
        new_count = len(new_deals)
        if new_count > 0:
            ranked_new_deals = self._rank_new_deals(new_deals, profile=profile, now=current_time)
            return NewDealsResult(
                last_seen_at=last_seen_at,
                new_count=new_count,
                fallback_used=False,
                deals=ranked_new_deals[:limit],
            )

        fallback_candidates = self._fallback_candidates(
            published_deals,
            profile=profile,
            last_seen_at=last_seen_at,
            now=current_time,
        )
        ranked_fallback = self._rank_fallback(fallback_candidates, profile=profile, now=current_time)
        return NewDealsResult(
            last_seen_at=last_seen_at,
            new_count=0,
            fallback_used=True,
            deals=ranked_fallback[:limit],
        )

    def mark_seen(
        self,
        db: Session,
        *,
        user: User,
        seen_at: datetime | None = None,
    ) -> datetime:
        normalized_seen_at = self._normalize_last_seen(seen_at or datetime.now(UTC))
        user.last_seen_deals_at = normalized_seen_at
        db.add(user)
        db.flush()
        return normalized_seen_at

    def _rank_new_deals(
        self,
        deals: list[DealRecord],
        *,
        profile,
        now: datetime,
    ) -> list[DealRecord]:
        if profile.has_personalization:
            return self.personalization_service.rank_new_deals_for_user(deals, profile=profile, now=now)
        return self.personalization_service.rank_default_new_feed(deals, now=now)

    def _rank_fallback(
        self,
        deals: list[DealRecord],
        *,
        profile,
        now: datetime,
    ) -> list[DealRecord]:
        if profile.has_personalization:
            return self.personalization_service.rank_deals_for_user(deals, profile=profile, now=now)
        return self.personalization_service.rank_default_feed(deals, now=now)

    def _interacted_deal_ids(self, db: Session, *, user: User) -> set[object]:
        event_types = (
            EVENT_DEAL_IMPRESSION,
            EVENT_RECOMMENDED_DEAL_IMPRESSION,
            EVENT_DEAL_CLICK,
            EVENT_RECOMMENDED_DEAL_CLICK,
        )
        rows = db.execute(
            select(UserEvent.deal_id).where(
                UserEvent.user_id == user.id,
                UserEvent.event_type.in_(event_types),
                UserEvent.deal_id.is_not(None),
            )
        ).all()
        return {row[0] for row in rows if row[0] is not None}

    def _fallback_candidates(
        self,
        deals: list[DealRecord],
        *,
        profile,
        last_seen_at: datetime,
        now: datetime,
    ) -> list[DealRecord]:
        recent_floor = now - NEW_DEALS_FALLBACK_LOOKBACK
        category_pool = [
            deal
            for deal in deals
            if self.personalization_service.freshness_datetime(deal) >= recent_floor
            if self.personalization_service.freshness_datetime(deal) <= last_seen_at
            if self._deal_matches_profile_categories(deal, profile=profile)
        ]
        if category_pool:
            return category_pool

        recent_pool = [
            deal
            for deal in deals
            if self.personalization_service.freshness_datetime(deal) >= recent_floor
            if self.personalization_service.freshness_datetime(deal) <= last_seen_at
        ]
        if recent_pool:
            return recent_pool
        return deals

    def _deal_matches_profile_categories(self, deal: DealRecord, *, profile) -> bool:
        preferred_categories = set(profile.categories).union(profile.seed_categories)
        if not preferred_categories:
            return False
        inferred_categories = set(infer_preference_categories_for_deal(deal))
        return bool(inferred_categories & preferred_categories)

    def _normalize_last_seen(self, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
