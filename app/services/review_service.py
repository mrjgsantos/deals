from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.enums import DealStatus, ReviewStatus, ReviewType
from app.db.models import Deal, ReviewQueue


@dataclass(slots=True)
class ReviewDecisionResult:
    review_id: UUID
    review_status: str
    deal_id: UUID
    deal_status: str


class ReviewService:
    def approve(self, db: Session, review_id: UUID) -> ReviewDecisionResult:
        review_item, deal = self._get_review_item_and_deal(db, review_id)
        review_item.status = ReviewStatus.RESOLVED
        review_item.resolved_at = datetime.now(timezone.utc)
        deal.status = DealStatus.APPROVED
        db.add(review_item)
        db.add(deal)
        db.commit()
        db.refresh(review_item)
        db.refresh(deal)
        return ReviewDecisionResult(
            review_id=review_item.id,
            review_status=review_item.status.value,
            deal_id=deal.id,
            deal_status=deal.status.value,
        )

    def reject(self, db: Session, review_id: UUID) -> ReviewDecisionResult:
        review_item, deal = self._get_review_item_and_deal(db, review_id)
        review_item.status = ReviewStatus.DISMISSED
        review_item.resolved_at = datetime.now(timezone.utc)
        deal.status = DealStatus.REJECTED
        db.add(review_item)
        db.add(deal)
        db.commit()
        db.refresh(review_item)
        db.refresh(deal)
        return ReviewDecisionResult(
            review_id=review_item.id,
            review_status=review_item.status.value,
            deal_id=deal.id,
            deal_status=deal.status.value,
        )

    def _get_review_item_and_deal(self, db: Session, review_id: UUID) -> tuple[ReviewQueue, Deal]:
        review_item = db.get(ReviewQueue, review_id)
        if review_item is None:
            raise ValueError("review_not_found")
        if review_item.entity_type != ReviewType.DEAL_VALIDATION:
            raise ValueError("unsupported_review_type")
        if review_item.status != ReviewStatus.PENDING:
            raise ValueError("review_already_resolved")
        deal = db.get(Deal, review_item.entity_id)
        if deal is None:
            raise ValueError("deal_not_found")
        if deal.status != DealStatus.PENDING_REVIEW:
            raise ValueError("invalid_deal_state")
        return review_item, deal
