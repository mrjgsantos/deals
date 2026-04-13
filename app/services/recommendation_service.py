from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.db.enums import DealStatus
from app.db.models import User
from app.services.deal_service import DealQueryService, DealRecord
from app.services.personalization import PersonalizationService, infer_preference_categories_for_deal
from app.services.saved_deals_service import SavedDealsService


@dataclass(slots=True)
class RecommendedDealsResult:
    categories: list[str]
    deals: list[DealRecord]


class RecommendationService:
    def __init__(self) -> None:
        self.deal_query_service = DealQueryService()
        self.saved_deals_service = SavedDealsService()
        self.personalization_service = PersonalizationService()

    def get_recommended_deals(self, db: Session, *, user: User, limit: int = 6) -> RecommendedDealsResult:
        saved_deals = self.saved_deals_service.list_saved_deals(db, user=user)
        saved_deal_ids = {item.deal.id for item in saved_deals}

        seed_categories: set[str] = set()
        for item in saved_deals:
            seed_categories.update(infer_preference_categories_for_deal(item.deal))

        profile = self.personalization_service.load_profile(db, user=user, seed_categories=seed_categories)
        if not profile.has_personalization:
            return RecommendedDealsResult(categories=[], deals=[])

        published_deals = [
            deal
            for deal in self.deal_query_service.list_deals(db)
            if deal.status in {DealStatus.APPROVED.value, DealStatus.PUBLISHED.value}
            if deal.published_at is not None
            if deal.id not in saved_deal_ids
        ]

        ranked_deals = self.personalization_service.rank_deals_for_user(
            published_deals,
            profile=profile,
        )
        return RecommendedDealsResult(
            categories=sorted(set(profile.categories).union(profile.seed_categories)),
            deals=ranked_deals[:limit],
        )
