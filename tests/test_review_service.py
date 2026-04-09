from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from app.db.enums import DealStatus, ReviewStatus, ReviewType
from app.db.models import Deal, ReviewQueue
from app.services.review_service import ReviewService


class FakeSession:
    def __init__(self, review_item: ReviewQueue, deal: Deal):
        self.review_item = review_item
        self.deal = deal
        self.committed = False
        self.refreshed = []
        self.added = []

    def get(self, model, entity_id):
        if model is ReviewQueue and entity_id == self.review_item.id:
            return self.review_item
        if model is Deal and entity_id == self.deal.id:
            return self.deal
        if model is Deal and entity_id == self.review_item.entity_id:
            return self.deal
        return None

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.committed = True

    def refresh(self, obj):
        self.refreshed.append(obj)


def make_deal() -> Deal:
    return Deal(
        id=uuid4(),
        source_id=uuid4(),
        title="Royal Canin Mini Adult 2x8kg",
        status=DealStatus.PENDING_REVIEW,
        currency="EUR",
        current_price="59.99",
    )


def make_review_queue(deal_id) -> ReviewQueue:
    return ReviewQueue(
        id=uuid4(),
        entity_type=ReviewType.DEAL_VALIDATION,
        entity_id=deal_id,
        status=ReviewStatus.PENDING,
        priority=100,
        reason="auto_generated_deal_review",
        payload={},
        created_at=datetime.now(timezone.utc),
    )


def test_approve_updates_deal_and_review_queue_states() -> None:
    deal = make_deal()
    review_item = make_review_queue(deal.id)
    db = FakeSession(review_item, deal)

    result = ReviewService().approve(db, review_item.id)

    assert result.review_status == "resolved"
    assert result.deal_status == "approved"
    assert review_item.status == ReviewStatus.RESOLVED
    assert review_item.resolved_at is not None
    assert deal.status == DealStatus.APPROVED
    assert db.committed is True


def test_reject_updates_deal_and_review_queue_states() -> None:
    deal = make_deal()
    review_item = make_review_queue(deal.id)
    db = FakeSession(review_item, deal)

    result = ReviewService().reject(db, review_item.id)

    assert result.review_status == "dismissed"
    assert result.deal_status == "rejected"
    assert review_item.status == ReviewStatus.DISMISSED
    assert review_item.resolved_at is not None
    assert deal.status == DealStatus.REJECTED
    assert db.committed is True


def test_approve_rejects_already_resolved_review() -> None:
    deal = make_deal()
    review_item = make_review_queue(deal.id)
    review_item.status = ReviewStatus.RESOLVED
    db = FakeSession(review_item, deal)

    try:
        ReviewService().approve(db, review_item.id)
    except ValueError as exc:
        assert str(exc) == "review_already_resolved"
    else:
        raise AssertionError("expected review_already_resolved")


def test_reject_rejects_invalid_deal_state() -> None:
    deal = make_deal()
    deal.status = DealStatus.APPROVED
    review_item = make_review_queue(deal.id)
    db = FakeSession(review_item, deal)

    try:
        ReviewService().reject(db, review_item.id)
    except ValueError as exc:
        assert str(exc) == "invalid_deal_state"
    else:
        raise AssertionError("expected invalid_deal_state")
