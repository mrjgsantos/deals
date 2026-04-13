from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.db.enums import DealStatus
from app.db.models import Deal, ProductVariant, SavedDeal, User
from app.services.deal_service import DealQueryService, DealRecord
from app.services.personalization import PersonalizationService


@dataclass(slots=True)
class SavedDealRecord:
    saved_at: datetime
    deal: DealRecord


@dataclass(slots=True)
class SavedDealMutationResult:
    deal_id: UUID
    saved: bool


class SavedDealsService:
    def __init__(self) -> None:
        self.deal_query_service = DealQueryService()
        self.personalization_service = PersonalizationService()

    def save_deal(self, db: Session, *, user: User, deal_id: UUID) -> SavedDealMutationResult:
        deal = self._get_saveable_deal(db, deal_id)
        if deal is None:
            raise ValueError("deal_not_found")

        existing = db.scalar(
            select(SavedDeal).where(
                SavedDeal.user_id == user.id,
                SavedDeal.deal_id == deal.id,
            )
        )
        if existing is None:
            db.add(SavedDeal(user_id=user.id, deal_id=deal.id))
            db.flush()
            self.personalization_service.record_save(db, user=user, deal_id=deal)
        return SavedDealMutationResult(deal_id=deal.id, saved=True)

    def unsave_deal(self, db: Session, *, user: User, deal_id: UUID) -> SavedDealMutationResult:
        db.execute(
            delete(SavedDeal).where(
                SavedDeal.user_id == user.id,
                SavedDeal.deal_id == deal_id,
            )
        )
        db.flush()
        return SavedDealMutationResult(deal_id=deal_id, saved=False)

    def list_saved_deals(self, db: Session, *, user: User) -> list[SavedDealRecord]:
        stmt = (
            select(SavedDeal)
            .join(Deal, Deal.id == SavedDeal.deal_id)
            .options(selectinload(SavedDeal.deal).selectinload(Deal.ai_copy_drafts))
            .where(
                SavedDeal.user_id == user.id,
                Deal.published_at.is_not(None),
                Deal.status.in_([DealStatus.APPROVED, DealStatus.PUBLISHED]),
            )
            .order_by(SavedDeal.created_at.desc())
        )
        saved_deals = db.scalars(stmt).all()
        return [
            SavedDealRecord(
                saved_at=item.created_at,
                deal=self.deal_query_service._to_record(item.deal),
            )
            for item in saved_deals
            if item.deal is not None
        ]

    def _get_saveable_deal(self, db: Session, deal_id: UUID) -> Deal | None:
        stmt = (
            select(Deal)
            .where(
                Deal.id == deal_id,
                Deal.published_at.is_not(None),
                Deal.status.in_([DealStatus.APPROVED, DealStatus.PUBLISHED]),
            )
            .options(selectinload(Deal.ai_copy_drafts))
            .options(selectinload(Deal.product_variant).selectinload(ProductVariant.product))
            .options(selectinload(Deal.product_source_record))
        )
        return db.scalar(stmt)
