from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.dependencies import (
    get_auth_service,
    get_current_user,
    get_deal_publication_service,
    get_deal_query_service,
    get_google_identity_service,
    get_metrics_service,
    get_new_deals_service,
    get_optional_current_user,
    get_personalization_service,
    get_product_analytics_service,
    get_recommendation_service,
    get_review_service,
    get_saved_deals_service,
    get_tracked_product_operations_service,
    get_user_preferences_service,
)
from app.db.session import get_db
from app.main import app
from app.services.auth_service import AuthResult
from app.services.deal_service import DealRecord, ReviewQueueRecord
from app.services.google_identity_service import GoogleIdentity
from app.services.metrics_service import MetricsOverviewRecord, SourceMetricsRecord
from app.services.new_deals_service import NewDealsResult
from app.services.personalization import PersonalizationProfile
from app.services.product_analytics_service import (
    ProductAnalyticsDealPerformanceRecord,
    ProductAnalyticsOverviewRecord,
)
from app.services.recommendation_service import RecommendedDealsResult
from app.services.saved_deals_service import SavedDealMutationResult, SavedDealRecord
from app.services.tracked_product_service import (
    TrackedProductOperationsRecord,
    TrackedProductOperationsSummaryRecord,
)
from app.services.user_preferences_service import UserPreferencesRecord


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

    def list_published_deals_page(self, db, *, limit, cursor_published_at=None, cursor_id=None):
        published = [
            deal
            for deal in self.deals
            if deal.status in {"approved", "published"} and deal.published_at is not None
        ]
        published.sort(key=lambda deal: (deal.published_at, deal.id), reverse=True)
        if cursor_published_at is not None and cursor_id is not None:
            published = [
                deal
                for deal in published
                if (deal.published_at < cursor_published_at)
                or (deal.published_at == cursor_published_at and deal.id < cursor_id)
            ]
        page_rows = published[: limit + 1]
        has_more = len(page_rows) > limit
        items = page_rows[:limit]
        next_row = items[-1] if has_more and items else None
        return type(
            "PublishedDealsPage",
            (),
            {
                "deals": items,
                "has_more": has_more,
                "next_published_at": getattr(next_row, "published_at", None),
                "next_id": getattr(next_row, "id", None),
            },
        )()


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


class FakeProductAnalyticsService:
    def __init__(self, overview: ProductAnalyticsOverviewRecord | None = None) -> None:
        self.overview = overview or ProductAnalyticsOverviewRecord(
            days=30,
            user_signups=4,
            onboarding_completed=3,
            deal_impressions=40,
            deal_clicks=8,
            deal_saves=4,
            deal_unsaves=1,
            recommended_deal_impressions=10,
            recommended_deal_clicks=3,
            ctr=0.2,
            save_rate=0.1,
            recommendation_ctr=0.3,
            top_deals=[
                ProductAnalyticsDealPerformanceRecord(
                    deal_id=uuid4(),
                    title="Logitech monitor",
                    category="Tech",
                    impression_count=10,
                    click_count=3,
                    save_count=2,
                    unsave_count=0,
                    recommended_impression_count=4,
                    recommended_click_count=2,
                    ctr=0.3,
                    save_rate=0.2,
                    recommended_ctr=0.5,
                )
            ],
        )

    def record_event(self, db, *, user_id, event_type, deal_id=None, occurred_at=None):
        return None

    def record_impressions(self, db, *, user_id, deal_ids, recommended=False):
        return len(list(dict.fromkeys(deal_ids)))

    def get_overview(self, db, *, days=30, limit=10):
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


class FakeAuthService:
    def __init__(self) -> None:
        self.user = type(
            "AuthUser",
            (),
            {
                "id": uuid4(),
                "email": "reviewer@example.com",
                "display_name": "Reviewer",
                "avatar_url": None,
                "created_at": datetime(2026, 4, 10, 9, 0, tzinfo=UTC),
                "is_staff": True,
                "email_verified_at": None,
            },
        )()

    def register(self, db, *, email, password):
        if email == "existing@example.com":
            raise ValueError("email_already_registered")
        self.user.email = email
        return AuthResult(access_token="register-token", token_type="bearer", user=self.user)

    def login(self, db, *, email, password):
        if password != "correct-password":
            raise ValueError("invalid_credentials")
        self.user.email = email
        return AuthResult(access_token="login-token", token_type="bearer", user=self.user)

    def create_email_verification_token(self, db, *, user_id):
        return "fake-verification-token"

    def login_with_google(self, db, *, identity):
        self.user.email = identity.email
        self.user.display_name = identity.name
        self.user.avatar_url = identity.picture
        return AuthResult(access_token="google-token", token_type="bearer", user=self.user, is_new_user=False)


class FakeGoogleIdentityService:
    def __init__(self, *, identity: GoogleIdentity | None = None, error: str | None = None) -> None:
        self.identity = identity or GoogleIdentity(
            sub="google-sub-123",
            email="reviewer@example.com",
            email_verified=True,
            name="Reviewer",
            picture="https://example.com/avatar.png",
        )
        self.error = error

    def verify_id_token(self, id_token: str) -> GoogleIdentity:
        if self.error is not None:
            raise ValueError(self.error)
        return self.identity


class FakeSavedDealsService:
    def __init__(self, *, items: list[SavedDealRecord] | None = None, error: str | None = None) -> None:
        self.items = items or []
        self.error = error

    def save_deal(self, db, *, user, deal_id):
        if self.error:
            raise ValueError(self.error)
        return SavedDealMutationResult(deal_id=deal_id, saved=True)

    def unsave_deal(self, db, *, user, deal_id):
        return SavedDealMutationResult(deal_id=deal_id, saved=False)

    def list_saved_deals(self, db, *, user):
        return self.items


class FakeRecommendationService:
    def __init__(self, deals: list[DealRecord]) -> None:
        self.deals = deals

    def get_recommended_deals(self, db, *, user, limit=6):
        return RecommendedDealsResult(categories=["Tech"], deals=self.deals[:limit])


class FakeNewDealsService:
    def __init__(self, result: NewDealsResult | None = None) -> None:
        self.result = result or NewDealsResult(
            last_seen_at=datetime(2026, 4, 11, 8, 0, tzinfo=UTC),
            new_count=1,
            fallback_used=False,
            deals=[make_deal_record(status="published", published_at=datetime(2026, 4, 11, 9, 0, tzinfo=UTC))],
        )

    def get_new_deals(self, db, *, user, limit=12, now=None):
        return self.result

    def mark_seen(self, db, *, user, seen_at=None):
        return seen_at or datetime(2026, 4, 12, 9, 30, tzinfo=UTC)


class FakePersonalizationService:
    def __init__(self, *, preferred_categories: list[str] | None = None) -> None:
        self.preferred_categories = preferred_categories or []

    def load_profile(self, db, *, user, seed_categories=()):
        categories = tuple(self.preferred_categories)
        return PersonalizationProfile(
            categories=categories,
            seed_categories=tuple(seed_categories),
            budget_preference=None,
            intent=(),
            has_pets=False,
            has_kids=False,
            context_flags={},
            category_affinity={},
            saved_count_by_category={},
            clicked_count_by_category={},
            negative_affinity={},
            last_interacted_at_by_category={},
        )

    def rank_deals_for_user(self, deals, *, profile, now=None):
        preferred = set(profile.categories) | set(profile.seed_categories)
        if not preferred:
            return self.rank_default_feed(deals, now=now)
        return sorted(
            deals,
            key=lambda deal: (
                deal.category in preferred,
                deal.published_at or deal.detected_at,
            ),
            reverse=True,
        )

    def rank_default_feed(self, deals, *, now=None):
        return sorted(deals, key=lambda deal: deal.published_at or deal.detected_at, reverse=True)

    def record_click(self, db, *, user, deal_id):
        return None


class FakeUserPreferencesService:
    def __init__(self, categories: list[str] | None = None) -> None:
        self.categories = categories or []

    def get_preferences(self, db, *, user):
        return UserPreferencesRecord(categories=self.categories, is_profile_initialized=bool(self.categories))

    def save_preferences(
        self,
        db,
        *,
        user,
        categories,
        budget_preference=None,
        intent=None,
        has_pets=False,
        has_kids=False,
        context_flags=None,
    ):
        self.categories = list(dict.fromkeys(categories))
        return UserPreferencesRecord(
            categories=self.categories,
            budget_preference=budget_preference,
            intent=intent or [],
            has_pets=has_pets,
            has_kids=has_kids,
            context_flags=context_flags or {},
            is_profile_initialized=True,
        )


def override_db():
    yield None


class FakeDBSession:
    def add(self, instance) -> None:
        return None

    def flush(self) -> None:
        return None

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None

    def refresh(self, instance) -> None:
        return None


def override_writable_db():
    yield FakeDBSession()


def override_authenticated_user():
    return type(
        "AuthUser",
        (),
        {
            "id": uuid4(),
            "email": "reviewer@example.com",
            "display_name": "Reviewer",
            "avatar_url": None,
            "created_at": datetime(2026, 4, 10, 9, 0, tzinfo=UTC),
            "is_staff": True,
            "email_verified_at": None,
        },
    )()


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
        "category": "Tech",
        "source_category": "Electronics",
        "subcategories": [],
        "asin": "B0TEST1234",
        "personalization_score": None,
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
    app.dependency_overrides[get_current_user] = override_authenticated_user
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


def test_register_returns_token_and_user() -> None:
    app.dependency_overrides[get_db] = override_writable_db
    app.dependency_overrides[get_auth_service] = lambda: FakeAuthService()
    client = TestClient(app)

    response = client.post(
        "/api/v1/auth/register",
        json={"email": "Reviewer@example.com", "password": "correct-password"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["access_token"] == "register-token"
    assert body["token_type"] == "bearer"
    assert body["user"]["email"] == "reviewer@example.com"
    app.dependency_overrides.clear()


def test_login_rejects_invalid_credentials() -> None:
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_auth_service] = lambda: FakeAuthService()
    client = TestClient(app)

    response = client.post(
        "/api/v1/auth/login",
        json={"email": "reviewer@example.com", "password": "wrong-password"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "invalid_credentials"
    app.dependency_overrides.clear()


def test_get_me_returns_authenticated_user() -> None:
    user = type(
        "AuthUser",
        (),
        {
            "id": uuid4(),
            "email": "reviewer@example.com",
            "display_name": "Reviewer",
            "avatar_url": None,
            "created_at": datetime(2026, 4, 10, 9, 0, tzinfo=UTC),
            "is_staff": True,
            "email_verified_at": None,
        },
    )()
    app.dependency_overrides[get_current_user] = lambda: user
    client = TestClient(app)

    response = client.get("/api/v1/auth/me")

    assert response.status_code == 200
    assert response.json()["email"] == "reviewer@example.com"
    app.dependency_overrides.clear()


def test_google_login_returns_token_and_user() -> None:
    app.dependency_overrides[get_db] = override_writable_db
    app.dependency_overrides[get_auth_service] = lambda: FakeAuthService()
    app.dependency_overrides[get_google_identity_service] = lambda: FakeGoogleIdentityService()
    client = TestClient(app)

    response = client.post("/api/v1/auth/google", json={"id_token": "google-id-token"})

    assert response.status_code == 200
    body = response.json()
    assert body["access_token"] == "google-token"
    assert body["user"]["email"] == "reviewer@example.com"
    assert body["is_new_user"] is False
    app.dependency_overrides.clear()


def test_google_login_rejects_invalid_token() -> None:
    app.dependency_overrides[get_db] = override_writable_db
    app.dependency_overrides[get_auth_service] = lambda: FakeAuthService()
    app.dependency_overrides[get_google_identity_service] = lambda: FakeGoogleIdentityService(error="invalid_google_token")
    client = TestClient(app)

    response = client.post("/api/v1/auth/google", json={"id_token": "bad-token"})

    assert response.status_code == 401
    assert response.json()["detail"] == "invalid_google_token"
    app.dependency_overrides.clear()


def test_internal_routes_require_authentication() -> None:
    client = TestClient(app)

    response = client.get("/api/v1/deals")

    assert response.status_code == 401
    assert response.json()["detail"] == "not_authenticated"
    app.dependency_overrides.clear()


def test_list_deals_returns_serialized_records() -> None:
    deal = make_deal_record()
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_authenticated_user
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
    app.dependency_overrides[get_current_user] = override_authenticated_user
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
    app.dependency_overrides[get_current_user] = override_authenticated_user
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
    app.dependency_overrides[get_personalization_service] = lambda: FakePersonalizationService()
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


def test_list_published_deals_boosts_matching_categories_for_authenticated_user() -> None:
    gaming_deal = make_deal_record(
        status="published",
        title="PlayStation controller bundle",
        category="Gaming",
        source_category="Gaming Accessories",
        detected_at=datetime(2026, 4, 9, 10, 0, tzinfo=UTC),
        published_at=datetime(2026, 4, 9, 10, 0, tzinfo=UTC),
    )
    home_deal = make_deal_record(
        status="published",
        title="Cordless vacuum for home",
        category="Home",
        source_category="Home Appliances",
        detected_at=datetime(2026, 4, 10, 10, 0, tzinfo=UTC),
        published_at=datetime(2026, 4, 10, 10, 0, tzinfo=UTC),
    )
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_optional_current_user] = override_authenticated_user
    app.dependency_overrides[get_personalization_service] = lambda: FakePersonalizationService(
        preferred_categories=["Gaming"]
    )
    app.dependency_overrides[get_deal_query_service] = lambda: FakeDealQueryService([home_deal, gaming_deal])
    client = TestClient(app)

    response = client.get("/api/v1/published-deals")

    assert response.status_code == 200
    body = response.json()
    assert [item["id"] for item in body] == [str(gaming_deal.id), str(home_deal.id)]
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
    app.dependency_overrides[get_personalization_service] = lambda: FakePersonalizationService()
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
    app.dependency_overrides[get_personalization_service] = lambda: FakePersonalizationService()
    app.dependency_overrides[get_deal_query_service] = lambda: FakeDealQueryService([third, first, second])
    client = TestClient(app)

    response = client.get("/api/v1/published-deals/feed?limit=2")

    assert response.status_code == 200
    body = response.json()
    assert [item["id"] for item in body] == [str(first.id), str(second.id)]
    assert len(body) == 2
    app.dependency_overrides.clear()


def test_published_deals_page_returns_cursor_and_has_more() -> None:
    base_time = datetime(2026, 4, 8, 12, 0, tzinfo=UTC)
    first = make_deal_record(status="published", detected_at=base_time, published_at=base_time)
    second = make_deal_record(
        status="published",
        detected_at=base_time - timedelta(hours=1),
        published_at=base_time - timedelta(hours=1),
    )
    third = make_deal_record(
        status="published",
        detected_at=base_time - timedelta(hours=2),
        published_at=base_time - timedelta(hours=2),
    )
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_personalization_service] = lambda: FakePersonalizationService()
    app.dependency_overrides[get_deal_query_service] = lambda: FakeDealQueryService([third, first, second])
    client = TestClient(app)

    response = client.get("/api/v1/published-deals/page?limit=2")

    assert response.status_code == 200
    body = response.json()
    assert [item["id"] for item in body["items"]] == [str(first.id), str(second.id)]
    assert body["has_more"] is True
    assert isinstance(body["next_cursor"], str)
    app.dependency_overrides.clear()


def test_published_deals_page_uses_cursor_without_duplicates() -> None:
    base_time = datetime(2026, 4, 8, 12, 0, tzinfo=UTC)
    deals = [
        make_deal_record(
            status="published",
            detected_at=base_time - timedelta(hours=index),
            published_at=base_time - timedelta(hours=index),
        )
        for index in range(4)
    ]
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_personalization_service] = lambda: FakePersonalizationService()
    app.dependency_overrides[get_deal_query_service] = lambda: FakeDealQueryService(deals)
    client = TestClient(app)

    first_response = client.get("/api/v1/published-deals/page?limit=2")
    assert first_response.status_code == 200
    first_body = first_response.json()
    second_response = client.get(f"/api/v1/published-deals/page?limit=2&cursor={first_body['next_cursor']}")

    assert second_response.status_code == 200
    second_body = second_response.json()
    first_ids = [item["id"] for item in first_body["items"]]
    second_ids = [item["id"] for item in second_body["items"]]
    assert len(set(first_ids).intersection(second_ids)) == 0
    assert second_body["has_more"] is False
    app.dependency_overrides.clear()


def test_publish_deal_endpoint_marks_approved_deal_as_published() -> None:
    deal = make_deal_record(status="approved")
    published_at = datetime(2026, 4, 9, 12, 0, tzinfo=UTC)
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_authenticated_user
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
    app.dependency_overrides[get_current_user] = override_authenticated_user
    app.dependency_overrides[get_deal_publication_service] = lambda: FakeDealPublicationService(
        error="invalid_deal_state"
    )
    client = TestClient(app)

    response = client.post(f"/api/v1/deals/{deal.id}/publish")

    assert response.status_code == 409
    assert response.json()["detail"] == "invalid_deal_state"
    app.dependency_overrides.clear()


def test_save_deal_endpoint_marks_deal_saved() -> None:
    deal = make_deal_record(status="published", published_at=datetime(2026, 4, 10, 12, 0, tzinfo=UTC))
    app.dependency_overrides[get_db] = override_writable_db
    app.dependency_overrides[get_current_user] = override_authenticated_user
    app.dependency_overrides[get_saved_deals_service] = lambda: FakeSavedDealsService()
    client = TestClient(app)

    response = client.post(f"/api/v1/deals/{deal.id}/save")

    assert response.status_code == 200
    assert response.json() == {"deal_id": str(deal.id), "saved": True}
    app.dependency_overrides.clear()


def test_save_deal_endpoint_returns_404_when_deal_not_available() -> None:
    deal = make_deal_record(status="pending_review")
    app.dependency_overrides[get_db] = override_writable_db
    app.dependency_overrides[get_current_user] = override_authenticated_user
    app.dependency_overrides[get_saved_deals_service] = lambda: FakeSavedDealsService(error="deal_not_found")
    client = TestClient(app)

    response = client.post(f"/api/v1/deals/{deal.id}/save")

    assert response.status_code == 404
    assert response.json()["detail"] == "deal_not_found"
    app.dependency_overrides.clear()


def test_unsave_deal_endpoint_marks_deal_unsaved() -> None:
    deal = make_deal_record(status="published", published_at=datetime(2026, 4, 10, 12, 0, tzinfo=UTC))
    app.dependency_overrides[get_db] = override_writable_db
    app.dependency_overrides[get_current_user] = override_authenticated_user
    app.dependency_overrides[get_saved_deals_service] = lambda: FakeSavedDealsService()
    client = TestClient(app)

    response = client.delete(f"/api/v1/deals/{deal.id}/save")

    assert response.status_code == 200
    assert response.json() == {"deal_id": str(deal.id), "saved": False}
    app.dependency_overrides.clear()


def test_track_deal_click_endpoint_returns_success() -> None:
    deal = make_deal_record(status="published", published_at=datetime(2026, 4, 10, 12, 0, tzinfo=UTC))
    app.dependency_overrides[get_db] = override_writable_db
    app.dependency_overrides[get_current_user] = override_authenticated_user
    app.dependency_overrides[get_personalization_service] = lambda: FakePersonalizationService()
    client = TestClient(app)

    response = client.post(f"/api/v1/deals/{deal.id}/click")

    assert response.status_code == 200
    assert response.json() == {"deal_id": str(deal.id), "clicked": True}
    app.dependency_overrides.clear()


def test_get_saved_deals_returns_saved_items() -> None:
    deal = make_deal_record(status="published", published_at=datetime(2026, 4, 10, 12, 0, tzinfo=UTC))
    saved_item = SavedDealRecord(
        saved_at=datetime(2026, 4, 10, 13, 0, tzinfo=UTC),
        deal=deal,
    )
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_authenticated_user
    app.dependency_overrides[get_saved_deals_service] = lambda: FakeSavedDealsService(items=[saved_item])
    client = TestClient(app)

    response = client.get("/api/v1/me/saved-deals")

    assert response.status_code == 200
    body = response.json()
    assert body[0]["saved_at"] == "2026-04-10T13:00:00Z"
    assert body[0]["deal"]["id"] == str(deal.id)
    assert body[0]["deal"]["published_at"] == "2026-04-10T12:00:00Z"
    app.dependency_overrides.clear()


def test_get_recommended_deals_returns_matching_published_items() -> None:
    recommended = make_deal_record(
        status="published",
        title="Wireless earbuds deal",
        category="Tech",
        source_category="Audio",
        published_at=datetime(2026, 4, 10, 12, 0, tzinfo=UTC),
    )
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_authenticated_user
    app.dependency_overrides[get_recommendation_service] = lambda: FakeRecommendationService([recommended])
    client = TestClient(app)

    response = client.get("/api/v1/me/recommended-deals")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == str(recommended.id)
    assert body[0]["published_at"] == "2026-04-10T12:00:00Z"
    app.dependency_overrides.clear()


def test_get_new_deals_returns_count_and_payload() -> None:
    new_deal = make_deal_record(
        status="published",
        title="Wireless earbuds deal",
        category="Tech",
        source_category="Audio",
        published_at=datetime(2026, 4, 12, 8, 0, tzinfo=UTC),
    )
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_authenticated_user
    app.dependency_overrides[get_new_deals_service] = lambda: FakeNewDealsService(
        NewDealsResult(
            last_seen_at=datetime(2026, 4, 11, 8, 0, tzinfo=UTC),
            new_count=3,
            fallback_used=False,
            deals=[new_deal],
        )
    )
    client = TestClient(app)

    response = client.get("/api/v1/me/new-deals")

    assert response.status_code == 200
    assert response.json() == {
        "new_count": 3,
        "fallback_used": False,
        "last_seen_at": "2026-04-11T08:00:00Z",
        "deals": [
            {
                "id": str(new_deal.id),
                "title": new_deal.title,
                "currency": "EUR",
                "current_price": "59.99",
                "previous_price": "79.99",
                "savings_amount": "20.00",
                "savings_percent": "25.00",
                "deal_url": "https://example.com/deal",
                "summary": "Structured summary",
                "image_url": None,
                "detected_at": new_deal.detected_at.isoformat().replace("+00:00", "Z"),
                "published_at": "2026-04-12T08:00:00Z",
                "category": "Tech",
                "subcategories": [],
                "personalization_score": None,
                "score_breakdown": {
                    "quality_score": 88,
                    "quality_reasons": ["strong_discount_vs_baseline", "fresh_price_drop"],
                    "business_score": 20,
                    "business_reasons": ["merchant_priority"],
                    "promotable": True,
                    "fake_discount": False,
                    "price_history": {
                        "avg_30d": "79.99",
                        "avg_90d": "82.99",
                        "min_90d": "59.99",
                        "max_90d": "95.99",
                        "all_time_min": "59.99",
                        "days_at_current_price": 2,
                        "observation_count_30d": 8,
                        "observation_count_90d": 24,
                        "observation_count_all_time": 40,
                    },
                },
                "ai_copy_draft": {
                    "id": new_deal.ai_copy_draft["id"],
                    "status": "draft",
                    "model_name": "stub-model",
                    "prompt_version": "v1",
                    "generated_at": new_deal.ai_copy_draft["generated_at"].isoformat().replace("+00:00", "Z"),
                    "content": {
                        "title": "Royal Canin Mini Adult 2x8kg for EUR 59.99",
                        "summary": "EUR 59.99 at Example Store.",
                        "verdict": "strong_value",
                        "tags": ["pet-food", "value"],
                    },
                    "warnings": [],
                },
            }
        ],
    }
    app.dependency_overrides.clear()


def test_mark_new_deals_seen_returns_last_seen_timestamp() -> None:
    app.dependency_overrides[get_db] = override_writable_db
    app.dependency_overrides[get_current_user] = override_authenticated_user
    app.dependency_overrides[get_new_deals_service] = lambda: FakeNewDealsService()
    client = TestClient(app)

    response = client.post("/api/v1/me/new-deals/mark-seen")

    assert response.status_code == 200
    assert response.json() == {"last_seen_at": "2026-04-12T09:30:00Z"}
    app.dependency_overrides.clear()


def test_track_deal_impressions_returns_tracked_count() -> None:
    app.dependency_overrides[get_db] = override_writable_db
    app.dependency_overrides[get_current_user] = override_authenticated_user
    app.dependency_overrides[get_product_analytics_service] = lambda: FakeProductAnalyticsService()
    client = TestClient(app)

    deal_one = str(uuid4())
    deal_two = str(uuid4())
    response = client.post(
        "/api/v1/me/deal-impressions",
        json={"deal_ids": [deal_one, deal_two, deal_one], "context": "recommended"},
    )

    assert response.status_code == 200
    assert response.json() == {"tracked": 2, "context": "recommended"}
    app.dependency_overrides.clear()


def test_get_preferences_returns_categories() -> None:
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_authenticated_user
    app.dependency_overrides[get_user_preferences_service] = lambda: FakeUserPreferencesService(["Tech", "Gaming"])
    client = TestClient(app)

    response = client.get("/api/v1/me/preferences")

    assert response.status_code == 200
    assert response.json() == {
        "categories": ["Tech", "Gaming"],
        "budget_preference": None,
        "intent": [],
        "has_pets": False,
        "has_kids": False,
        "context_flags": {},
        "category_affinity": {},
        "saved_count_by_category": {},
        "clicked_count_by_category": {},
        "negative_affinity": {},
        "is_profile_initialized": True,
    }
    app.dependency_overrides.clear()


def test_save_preferences_returns_normalized_categories() -> None:
    app.dependency_overrides[get_db] = override_writable_db
    app.dependency_overrides[get_current_user] = override_authenticated_user
    app.dependency_overrides[get_user_preferences_service] = lambda: FakeUserPreferencesService()
    client = TestClient(app)

    response = client.post(
        "/api/v1/me/preferences",
        json={
            "categories": ["Tech", "Gaming", "Tech"],
            "budget_preference": "medium",
            "intent": ["save_money", "practical"],
            "has_pets": True,
            "has_kids": False,
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "categories": ["Tech", "Gaming"],
        "budget_preference": "medium",
        "intent": ["save_money", "practical"],
        "has_pets": True,
        "has_kids": False,
        "context_flags": {},
        "category_affinity": {},
        "saved_count_by_category": {},
        "clicked_count_by_category": {},
        "negative_affinity": {},
        "is_profile_initialized": True,
    }
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
    app.dependency_overrides[get_current_user] = override_authenticated_user
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
    app.dependency_overrides[get_current_user] = override_authenticated_user
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


def test_product_analytics_metrics_returns_stable_shape() -> None:
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_authenticated_user
    app.dependency_overrides[get_product_analytics_service] = lambda: FakeProductAnalyticsService()
    client = TestClient(app)

    response = client.get("/api/v1/metrics/product-analytics")

    assert response.status_code == 200
    body = response.json()
    assert body["ctr"] == 0.2
    assert body["save_rate"] == 0.1
    assert body["recommendation_ctr"] == 0.3
    assert body["top_deals"][0]["title"] == "Logitech monitor"
    assert body["top_deals"][0]["recommended_ctr"] == 0.5
    app.dependency_overrides.clear()


def test_approve_review_endpoint() -> None:
    review_item = make_review_queue_record()
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_authenticated_user
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
    app.dependency_overrides[get_current_user] = override_authenticated_user
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
    app.dependency_overrides[get_current_user] = override_authenticated_user
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
    app.dependency_overrides[get_current_user] = override_authenticated_user
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
    app.dependency_overrides[get_current_user] = override_authenticated_user
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
