from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.dependencies import get_deal_query_service, get_review_service
from app.db.session import get_db
from app.main import app
from app.services.deal_service import DealRecord, ReviewQueueRecord


class FakeDealQueryService:
    def __init__(self, deals: list[DealRecord]) -> None:
        self.deals = deals

    def list_deals(self, db, *, status=None):
        if status is None:
            return self.deals
        return [deal for deal in self.deals if deal.status == status.value]

    def get_deal(self, db, deal_id):
        for deal in self.deals:
            if deal.id == deal_id:
                return deal
        return None


class FakeReviewService:
    def __init__(self, review_id, deal_id, error: str | None = None):
        self.review_id = review_id
        self.deal_id = deal_id
        self.error = error

    def approve(self, db, review_id):
        if self.error:
            raise ValueError(self.error)
        return type(
            "ReviewDecision",
            (),
            {
                "review_id": review_id,
                "review_status": "resolved",
                "deal_id": self.deal_id,
                "deal_status": "approved",
            },
        )()

    def reject(self, db, review_id):
        if self.error:
            raise ValueError(self.error)
        return type(
            "ReviewDecision",
            (),
            {
                "review_id": review_id,
                "review_status": "dismissed",
                "deal_id": self.deal_id,
                "deal_status": "rejected",
            },
        )()


def override_db():
    yield None


def make_deal_record(status: str = "pending_review") -> DealRecord:
    return DealRecord(
        id=uuid4(),
        title="Royal Canin Mini Adult 2x8kg",
        status=status,
        currency="EUR",
        current_price=Decimal("59.99"),
        previous_price=Decimal("79.99"),
        savings_amount=Decimal("20.00"),
        savings_percent=Decimal("25.00"),
        deal_url="https://example.com/deal",
        summary="Structured summary",
        source_id=uuid4(),
        product_variant_id=uuid4(),
        product_source_record_id=uuid4(),
        detected_at=datetime.now(UTC),
        score_breakdown={
            "quality_score": 88,
            "quality_reasons": ["strong_discount_vs_baseline", "fresh_price_drop"],
            "business_score": 20,
            "business_reasons": ["merchant_priority"],
            "promotable": True,
            "fake_discount": False,
        },
        ai_copy_draft={
            "id": str(uuid4()),
            "status": "draft",
            "model_name": "stub-model",
            "prompt_version": "v1",
            "generated_at": datetime.now(UTC),
            "content": {
                "title": "Royal Canin Mini Adult 2x8kg for EUR 59.99",
                "summary": "EUR 59.99 at Example Store.",
                "verdict": "strong_value",
                "tags": ["pet-food", "value"],
            },
            "warnings": [],
        },
    )


def make_review_queue_record(status: str = "pending") -> ReviewQueueRecord:
    return ReviewQueueRecord(
        id=uuid4(),
        status=status,
        reason="auto_generated_deal_review",
        priority=100,
        created_at=datetime.now(UTC),
        resolved_at=None,
        deal=make_deal_record(),
    )


def test_get_pending_review_includes_scores_and_ai_copy() -> None:
    review_item = make_review_queue_record()
    app.dependency_overrides[get_db] = override_db
    fake_service = FakeDealQueryService([])
    fake_service.list_pending_review_items = lambda db: [review_item]
    app.dependency_overrides[get_deal_query_service] = lambda: fake_service
    client = TestClient(app)

    response = client.get("/api/v1/review/pending")

    assert response.status_code == 200
    body = response.json()
    assert body[0]["status"] == "pending"
    assert body[0]["deal"]["score_breakdown"]["quality_score"] == 88
    assert body[0]["deal"]["ai_copy_draft"]["content"]["verdict"] == "strong_value"
    app.dependency_overrides.clear()


def test_list_deals_returns_serialized_records() -> None:
    deal = make_deal_record()
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_deal_query_service] = lambda: FakeDealQueryService([deal])
    client = TestClient(app)

    response = client.get("/api/v1/deals")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == str(deal.id)
    assert body[0]["score_breakdown"]["promotable"] is True
    assert "debug" not in body[0]
    app.dependency_overrides.clear()


def test_get_deal_by_id_returns_detail() -> None:
    deal = make_deal_record()
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_deal_query_service] = lambda: FakeDealQueryService([deal])
    client = TestClient(app)

    response = client.get(f"/api/v1/deals/{deal.id}")

    assert response.status_code == 200
    assert response.json()["id"] == str(deal.id)
    app.dependency_overrides.clear()


def test_get_deal_by_id_returns_404_when_missing() -> None:
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_deal_query_service] = lambda: FakeDealQueryService([])
    client = TestClient(app)

    response = client.get(f"/api/v1/deals/{uuid4()}")

    assert response.status_code == 404
    assert response.json()["detail"] == "deal_not_found"
    app.dependency_overrides.clear()


def test_approve_review_endpoint() -> None:
    review_item = make_review_queue_record()
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_review_service] = lambda: FakeReviewService(review_item.id, review_item.deal.id)
    client = TestClient(app)

    response = client.post(f"/api/v1/review/{review_item.id}/approve")

    assert response.status_code == 200
    assert response.json() == {
        "review_id": str(review_item.id),
        "review_status": "resolved",
        "deal_id": str(review_item.deal.id),
        "deal_status": "approved",
    }
    assert "debug" not in response.json()
    app.dependency_overrides.clear()


def test_reject_review_endpoint() -> None:
    review_item = make_review_queue_record()
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_review_service] = lambda: FakeReviewService(review_item.id, review_item.deal.id)
    client = TestClient(app)

    response = client.post(f"/api/v1/review/{review_item.id}/reject")

    assert response.status_code == 200
    assert response.json()["review_status"] == "dismissed"
    assert response.json()["deal_status"] == "rejected"
    app.dependency_overrides.clear()


def test_approve_review_endpoint_returns_409_when_already_resolved() -> None:
    review_item = make_review_queue_record()
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_review_service] = lambda: FakeReviewService(
        review_item.id,
        review_item.deal.id,
        error="review_already_resolved",
    )
    client = TestClient(app)

    response = client.post(f"/api/v1/review/{review_item.id}/approve")

    assert response.status_code == 409
    assert response.json()["detail"] == "review_already_resolved"
    app.dependency_overrides.clear()


def test_reject_review_endpoint_returns_409_for_invalid_deal_state() -> None:
    review_item = make_review_queue_record()
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_review_service] = lambda: FakeReviewService(
        review_item.id,
        review_item.deal.id,
        error="invalid_deal_state",
    )
    client = TestClient(app)

    response = client.post(f"/api/v1/review/{review_item.id}/reject")

    assert response.status_code == 409
    assert response.json()["detail"] == "invalid_deal_state"
    app.dependency_overrides.clear()


def test_approve_review_endpoint_returns_404_when_missing() -> None:
    review_item = make_review_queue_record()
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_review_service] = lambda: FakeReviewService(
        review_item.id,
        review_item.deal.id,
        error="review_not_found",
    )
    client = TestClient(app)

    response = client.post(f"/api/v1/review/{review_item.id}/approve")

    assert response.status_code == 404
    assert response.json()["detail"] == "review_not_found"
    app.dependency_overrides.clear()
