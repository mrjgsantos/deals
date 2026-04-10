from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.dependencies import (
    get_deal_publication_service,
    get_deal_query_service,
    get_metrics_service,
    get_review_service,
    get_tracked_product_operations_service,
)
from app.db.session import get_db
from app.main import app
from app.services.deal_service import DealRecord, ReviewQueueRecord
from app.services.metrics_service import MetricsOverviewRecord, SourceMetricsRecord
from app.services.tracked_product_service import (
    TrackedProductOperationsRecord,
    TrackedProductOperationsSummaryRecord,
)


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


class FakeDealPublicationService:
    def __init__(self, published_at: datetime | None = None, error: str | None = None):
        self.published_at = published_at or datetime(2026, 4, 9, 12, 0, tzinfo=UTC)
        self.error = error

    def mark_published(self, db, deal_id):
        if self.error:
            raise ValueError(self.error)
        return type(
            "DealPublicationResult",
            (),
            {
                "deal_id": deal_id,
                "deal_status": "published",
                "published_at": self.published_at,
            },
        )()


class FakeMetricsService:
    def __init__(self, overview: MetricsOverviewRecord):
        self.overview = overview

    def get_overview(self, db):
        return self.overview


class FakeTrackedProductOperationsService:
    def __init__(
        self,
        *,
        summary: TrackedProductOperationsSummaryRecord,
        items: list[TrackedProductOperationsRecord],
    ) -> None:
        self.summary = summary
        self.items = items

    def get_summary(self, db):
        return self.summary

    def list_operations(self, db, *, limit=200, refresh_interval_seconds=None):
        return self.items[:limit]


class FakeTrackedScheduler:
    def get_runtime_snapshot(self):
        return type(
            "TrackedSnapshot",
            (),
            {
                "interval_seconds": 600,
                "is_running": True,
                "last_started_at": datetime(2026, 4, 10, 8, 0, tzinfo=UTC),
                "last_completed_at": datetime(2026, 4, 10, 8, 1, tzinfo=UTC),
                "last_status": "completed_with_failures",
                "last_error_reason": None,
                "last_summary": type(
                    "TrackedSummary",
                    (),
                    {
                        "tracked_asins": 8,
                        "eligible_asins": 3,
                        "fetched_products": 3,
                        "accepted": 2,
                        "rejected": 1,
                        "failed_batches": 1,
                        "skipped_reason": None,
                    },
                )(),
            },
        )()


def override_db():
    yield None


def make_deal_record(status: str = "pending_review", **overrides) -> DealRecord:
    payload = {
        "id": uuid4(),
        "title": "Royal Canin Mini Adult 2x8kg",
        "status": status,
        "currency": "EUR",
        "current_price": Decimal("59.99"),
        "previous_price": Decimal("79.99"),
        "savings_amount": Decimal("20.00"),
        "savings_percent": Decimal("25.00"),
        "deal_url": "https://example.com/deal",
        "summary": "Structured summary",
        "source_id": uuid4(),
        "product_variant_id": uuid4(),
        "product_source_record_id": uuid4(),
        "detected_at": datetime.now(UTC),
        "published_at": None,
        "score_breakdown": {
            "quality_score": 88,
            "quality_reasons": ["strong_discount_vs_baseline", "fresh_price_drop"],
            "business_score": 20,
            "business_reasons": ["merchant_priority"],
            "promotable": True,
            "fake_discount": False,
            "price_history": {
                "avg_30d": Decimal("79.99"),
                "avg_90d": Decimal("82.99"),
                "min_90d": Decimal("59.99"),
                "max_90d": Decimal("95.99"),
                "all_time_min": Decimal("59.99"),
                "days_at_current_price": 2,
                "observation_count_30d": 8,
                "observation_count_90d": 24,
                "observation_count_all_time": 40,
            },
        },
        "ai_copy_draft": {
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
    }
    payload.update(overrides)
    return DealRecord(**payload)


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
    assert body[0]["published_at"] is None
    assert body[0]["score_breakdown"]["promotable"] is True
    assert body[0]["score_breakdown"]["price_history"]["observation_count_90d"] == 24
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
    assert response.json()["previous_price"] == "79.99"
    assert response.json()["savings_amount"] == "20.00"
    assert response.json()["score_breakdown"]["price_history"]["avg_30d"] == "79.99"
    app.dependency_overrides.clear()


def test_get_deal_by_id_returns_404_when_missing() -> None:
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_deal_query_service] = lambda: FakeDealQueryService([])
    client = TestClient(app)

    response = client.get(f"/api/v1/deals/{uuid4()}")

    assert response.status_code == 404
    assert response.json()["detail"] == "deal_not_found"
    app.dependency_overrides.clear()


def test_list_published_deals_returns_only_published_approved_records() -> None:
    published_approved_deal = make_deal_record(status="approved", published_at=datetime(2026, 4, 9, 10, 0, tzinfo=UTC))
    approved_unpublished_deal = make_deal_record(status="approved")
    pending_deal = make_deal_record(status="pending_review", published_at=datetime(2026, 4, 9, 11, 0, tzinfo=UTC))
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_deal_query_service] = lambda: FakeDealQueryService(
        [published_approved_deal, approved_unpublished_deal, pending_deal]
    )
    client = TestClient(app)

    response = client.get("/api/v1/published-deals")

    assert response.status_code == 200
    body = response.json()
    assert [item["id"] for item in body] == [str(published_approved_deal.id)]
    assert body[0]["title"] == published_approved_deal.title
    assert body[0]["published_at"] == "2026-04-09T10:00:00Z"
    assert body[0]["score_breakdown"]["quality_score"] == 88
    assert "status" not in body[0]
    assert "source_id" not in body[0]
    app.dependency_overrides.clear()


def test_get_published_deal_returns_published_approved_detail() -> None:
    deal = make_deal_record(status="approved", published_at=datetime(2026, 4, 9, 10, 0, tzinfo=UTC))
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_deal_query_service] = lambda: FakeDealQueryService([deal])
    client = TestClient(app)

    response = client.get(f"/api/v1/published-deals/{deal.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(deal.id)
    assert body["published_at"] == "2026-04-09T10:00:00Z"
    assert body["ai_copy_draft"]["content"]["verdict"] == "strong_value"
    assert "status" not in body
    app.dependency_overrides.clear()


def test_get_published_deal_returns_404_for_unpublished_approved_deal() -> None:
    deal = make_deal_record(status="approved")
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_deal_query_service] = lambda: FakeDealQueryService([deal])
    client = TestClient(app)

    response = client.get(f"/api/v1/published-deals/{deal.id}")

    assert response.status_code == 404
    assert response.json()["detail"] == "published_deal_not_found"
    app.dependency_overrides.clear()


def test_published_deals_feed_returns_approved_only_newest_first() -> None:
    older = make_deal_record(
        status="approved",
        detected_at=datetime(2026, 4, 8, 10, 0, tzinfo=UTC),
        published_at=datetime(2026, 4, 8, 10, 30, tzinfo=UTC),
    )
    newest = make_deal_record(
        status="approved",
        detected_at=datetime(2026, 4, 8, 12, 0, tzinfo=UTC),
        published_at=datetime(2026, 4, 8, 12, 30, tzinfo=UTC),
    )
    pending = make_deal_record(status="pending_review", detected_at=datetime(2026, 4, 8, 11, 0, tzinfo=UTC))
    approved_unpublished = make_deal_record(status="approved", detected_at=datetime(2026, 4, 8, 9, 0, tzinfo=UTC))
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_deal_query_service] = lambda: FakeDealQueryService(
        [older, pending, newest, approved_unpublished]
    )
    client = TestClient(app)

    response = client.get("/api/v1/published-deals/feed")

    assert response.status_code == 200
    body = response.json()
    assert [item["id"] for item in body] == [str(newest.id), str(older.id)]
    assert "score_breakdown" not in body[0]
    assert "ai_copy_draft" not in body[0]
    assert "status" not in body[0]
    assert body[0]["published_at"] == "2026-04-08T12:30:00Z"
    app.dependency_overrides.clear()


def test_published_deals_feed_applies_limit() -> None:
    base_time = datetime(2026, 4, 8, 12, 0, tzinfo=UTC)
    first = make_deal_record(
        status="approved",
        detected_at=base_time,
        published_at=base_time,
    )
    second = make_deal_record(
        status="approved",
        detected_at=base_time - timedelta(hours=1),
        published_at=base_time - timedelta(hours=1),
    )
    third = make_deal_record(
        status="approved",
        detected_at=base_time - timedelta(hours=2),
        published_at=base_time - timedelta(hours=2),
    )
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_deal_query_service] = lambda: FakeDealQueryService([third, first, second])
    client = TestClient(app)

    response = client.get("/api/v1/published-deals/feed?limit=2")

    assert response.status_code == 200
    body = response.json()
    assert [item["id"] for item in body] == [str(first.id), str(second.id)]
    assert len(body) == 2
    app.dependency_overrides.clear()


def test_publish_deal_endpoint_marks_approved_deal_as_published() -> None:
    deal = make_deal_record(status="approved")
    published_at = datetime(2026, 4, 9, 12, 0, tzinfo=UTC)
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_deal_publication_service] = lambda: FakeDealPublicationService(
        published_at=published_at
    )
    client = TestClient(app)

    response = client.post(f"/api/v1/deals/{deal.id}/publish")

    assert response.status_code == 200
    assert response.json() == {
        "deal_id": str(deal.id),
        "deal_status": "published",
        "published_at": "2026-04-09T12:00:00Z",
    }
    app.dependency_overrides.clear()


def test_publish_deal_endpoint_returns_409_for_non_approved_deal() -> None:
    deal = make_deal_record(status="pending_review")
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_deal_publication_service] = lambda: FakeDealPublicationService(
        error="invalid_deal_state"
    )
    client = TestClient(app)

    response = client.post(f"/api/v1/deals/{deal.id}/publish")

    assert response.status_code == 409
    assert response.json()["detail"] == "invalid_deal_state"
    app.dependency_overrides.clear()


def test_metrics_overview_returns_stable_shape() -> None:
    overview = MetricsOverviewRecord(
        total_sources=3,
        active_sources=2,
        raw_ingestion_records_total=120,
        raw_ingestion_records_recent=15,
        raw_ingestion_records_accepted=80,
        raw_ingestion_records_rejected=10,
        raw_ingestion_records_duplicate=20,
        raw_ingestion_records_failed=10,
        deals_total=25,
        deals_pending_review=4,
        deals_approved=12,
        deals_rejected=3,
        deals_published=6,
        review_queue_pending=4,
        breakdown_by_source=[
            SourceMetricsRecord(
                source_id=uuid4(),
                source_slug="serpapi-google-shopping",
                source_name="SerpApi Google Shopping",
                is_active=True,
                raw_ingestion_records_total=70,
                raw_ingestion_records_accepted=50,
                raw_ingestion_records_rejected=5,
                raw_ingestion_records_duplicate=10,
                raw_ingestion_records_failed=5,
                deals_total=15,
                deals_pending_review=3,
                deals_approved=8,
                deals_rejected=2,
                deals_published=4,
                review_queue_pending=3,
            )
        ],
    )
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_metrics_service] = lambda: FakeMetricsService(overview)
    client = TestClient(app)

    response = client.get("/api/v1/metrics/overview")

    assert response.status_code == 200
    body = response.json()
    assert body["total_sources"] == 3
    assert body["active_sources"] == 2
    assert body["raw_ingestion_records_total"] == 120
    assert body["raw_ingestion_records_recent"] == 15
    assert body["raw_ingestion_records_duplicate"] == 20
    assert body["raw_ingestion_records_failed"] == 10
    assert body["deals_approved"] == 12
    assert body["deals_published"] == 6
    assert body["review_queue_pending"] == 4
    assert body["breakdown_by_source"][0]["source_slug"] == "serpapi-google-shopping"
    assert body["breakdown_by_source"][0]["raw_ingestion_records_duplicate"] == 10
    assert body["breakdown_by_source"][0]["raw_ingestion_records_failed"] == 5
    assert body["breakdown_by_source"][0]["deals_pending_review"] == 3
    assert body["breakdown_by_source"][0]["deals_published"] == 4
    app.dependency_overrides.clear()


def test_tracked_products_metrics_returns_scheduler_and_items() -> None:
    tracked_item = TrackedProductOperationsRecord(
        id=uuid4(),
        asin="B0TRACK123",
        domain_id=9,
        display_name="Tracked Earbuds",
        source_slug="amazon-keepa",
        source_name="Amazon Keepa",
        source_url="https://www.amazon.es/dp/B0TRACK123",
        is_active=True,
        last_refresh_attempt_at=datetime(2026, 4, 10, 8, 0, tzinfo=UTC),
        last_successful_refresh_at=datetime(2026, 4, 10, 7, 50, tzinfo=UTC),
        last_failed_refresh_at=datetime(2026, 4, 10, 7, 0, tzinfo=UTC),
        refresh_status="fetch_failed",
        refresh_failure_reason="keepa_fetch_failed",
        consecutive_refresh_failures=2,
        next_refresh_earliest_at=datetime(2026, 4, 10, 8, 10, tzinfo=UTC),
        refresh_priority="high",
        staleness_classification="retry_backoff",
        observation_count_all_time=14,
        linked_deal_count=2,
        has_pending_review_deal=True,
        has_published_deal=True,
    )
    summary = TrackedProductOperationsSummaryRecord(
        total_tracked_products=8,
        active_tracked_products=8,
        never_attempted=2,
        in_progress=1,
        succeeded=4,
        failed=1,
        retry_backoff=1,
        due_now=2,
    )
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_tracked_product_operations_service] = lambda: FakeTrackedProductOperationsService(
        summary=summary,
        items=[tracked_item],
    )
    app.state.background_keepa_scheduler = FakeTrackedScheduler()
    client = TestClient(app)

    response = client.get("/api/v1/metrics/tracked-products")

    assert response.status_code == 200
    body = response.json()
    assert body["scheduler"]["enabled"] is True
    assert body["scheduler"]["last_status"] == "completed_with_failures"
    assert body["scheduler"]["tracked_asins"] == 8
    assert body["summary"]["failed"] == 1
    assert body["summary"]["retry_backoff"] == 1
    assert body["items"][0]["asin"] == "B0TRACK123"
    assert body["items"][0]["refresh_status"] == "fetch_failed"
    assert body["items"][0]["consecutive_refresh_failures"] == 2
    assert body["items"][0]["refresh_priority"] == "high"
    assert body["items"][0]["observation_count_all_time"] == 14
    assert body["items"][0]["has_published_deal"] is True

    del app.state.background_keepa_scheduler
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
