from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class HealthResponse(BaseModel):
    status: str


class AuthCredentialsRequest(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if not cleaned:
            raise ValueError("email is required")
        if len(cleaned) > 320:
            raise ValueError("email is too long")
        if "@" not in cleaned or cleaned.startswith("@") or cleaned.endswith("@"):
            raise ValueError("email must be valid")
        return cleaned

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if len(value) < 8:
            raise ValueError("password must be at least 8 characters")
        if len(value) > 255:
            raise ValueError("password is too long")
        return value


class ForgotPasswordRequest(BaseModel):
    email: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if not cleaned or "@" not in cleaned:
            raise ValueError("email must be valid")
        return cleaned


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

    @field_validator("token")
    @classmethod
    def validate_token(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("token is required")
        return cleaned

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, value: str) -> str:
        if len(value) < 8:
            raise ValueError("password must be at least 8 characters")
        if len(value) > 255:
            raise ValueError("password is too long")
        return value


class GoogleAuthRequest(BaseModel):
    id_token: str

    @field_validator("id_token")
    @classmethod
    def validate_id_token(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("id_token is required")
        return cleaned


class AuthUserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    display_name: str | None = None
    avatar_url: str | None = None
    email_verified: bool = False
    created_at: datetime

    @classmethod
    def model_validate(cls, obj, **kwargs):  # type: ignore[override]
        instance = super().model_validate(obj, **kwargs)
        instance.email_verified = getattr(obj, "email_verified_at", None) is not None
        return instance


class AuthTokenResponse(BaseModel):
    access_token: str
    token_type: str
    user: AuthUserResponse
    is_new_user: bool = False


class UserPreferencesRequest(BaseModel):
    categories: list[str] = Field(default_factory=list)
    budget_preference: str | None = None
    intent: list[str] = Field(default_factory=list)
    has_pets: bool = False
    has_kids: bool = False
    context_flags: dict[str, bool] = Field(default_factory=dict)

    @field_validator("categories")
    @classmethod
    def validate_categories(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value if item.strip()]
        if len(cleaned) > 12:
            raise ValueError("too many categories")
        return cleaned

    @field_validator("budget_preference")
    @classmethod
    def validate_budget_preference(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip().lower()
        if cleaned not in {"low", "medium", "high"}:
            raise ValueError("budget_preference must be low, medium, or high")
        return cleaned

    @field_validator("intent")
    @classmethod
    def validate_intent(cls, value: list[str]) -> list[str]:
        allowed = {"save_money", "discover_products", "upgrade_life", "practical"}
        cleaned: list[str] = []
        for item in value:
            normalized = item.strip().lower()
            if normalized and normalized in allowed and normalized not in cleaned:
                cleaned.append(normalized)
        if len(cleaned) > 8:
            raise ValueError("too many intent values")
        return cleaned

    @field_validator("context_flags")
    @classmethod
    def validate_context_flags(cls, value: dict[str, bool]) -> dict[str, bool]:
        cleaned: dict[str, bool] = {}
        for key, item in value.items():
            normalized_key = key.strip().lower().replace(" ", "_")
            if not normalized_key:
                continue
            cleaned[normalized_key[:64]] = bool(item)
        return cleaned


class UserPreferencesResponse(BaseModel):
    categories: list[str] = Field(default_factory=list)
    budget_preference: str | None = None
    intent: list[str] = Field(default_factory=list)
    has_pets: bool = False
    has_kids: bool = False
    context_flags: dict[str, bool] = Field(default_factory=dict)
    category_affinity: dict[str, float] = Field(default_factory=dict)
    saved_count_by_category: dict[str, int] = Field(default_factory=dict)
    clicked_count_by_category: dict[str, int] = Field(default_factory=dict)
    negative_affinity: dict[str, float] = Field(default_factory=dict)
    is_profile_initialized: bool = False


class NewDealsResponse(BaseModel):
    new_count: int = 0
    fallback_used: bool = False
    last_seen_at: datetime | None = None
    deals: list["PublishedDealResponse"] = Field(default_factory=list)


class NewDealsSeenResponse(BaseModel):
    last_seen_at: datetime


class DealImpressionRequest(BaseModel):
    deal_ids: list[UUID] = Field(default_factory=list)
    context: str = "feed"

    @field_validator("deal_ids")
    @classmethod
    def validate_deal_ids(cls, value: list[UUID]) -> list[UUID]:
        if len(value) > 100:
            raise ValueError("too many deal_ids")
        return value

    @field_validator("context")
    @classmethod
    def validate_context(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if cleaned not in {"feed", "recommended"}:
            raise ValueError("context must be feed or recommended")
        return cleaned


class DealImpressionResponse(BaseModel):
    tracked: int
    context: str


class SavedDealMutationResponse(BaseModel):
    deal_id: UUID
    saved: bool


class DealClickResponse(BaseModel):
    deal_id: UUID
    clicked: bool


class DealScoreBreakdownResponse(BaseModel):
    quality_score: int | None = None
    quality_reasons: list[str] = Field(default_factory=list)
    business_score: int | None = None
    business_reasons: list[str] = Field(default_factory=list)
    promotable: bool = False
    fake_discount: bool = False
    price_history: "DealPriceHistoryResponse | None" = None


class DealPriceHistoryResponse(BaseModel):
    avg_30d: Decimal | None = None
    avg_90d: Decimal | None = None
    min_90d: Decimal | None = None
    max_90d: Decimal | None = None
    all_time_min: Decimal | None = None
    days_at_current_price: int | None = None
    observation_count_30d: int = 0
    observation_count_90d: int = 0
    observation_count_all_time: int = 0


class AICopyDraftResponse(BaseModel):
    id: str
    status: str
    model_name: str | None = None
    prompt_version: str | None = None
    generated_at: datetime
    content: dict[str, Any]
    warnings: list[str] = Field(default_factory=list)


class DealResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    status: str
    currency: str
    current_price: Decimal
    previous_price: Decimal | None = None
    savings_amount: Decimal | None = None
    savings_percent: Decimal | None = None
    deal_url: str | None = None
    summary: str | None = None
    source_id: UUID
    product_variant_id: UUID | None = None
    product_source_record_id: UUID | None = None
    detected_at: datetime
    published_at: datetime | None = None
    category: str | None = None
    subcategories: list[str] = Field(default_factory=list)
    personalization_score: float | None = None
    score_breakdown: DealScoreBreakdownResponse
    ai_copy_draft: AICopyDraftResponse | None = None


class PublishedDealResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    currency: str
    current_price: Decimal
    previous_price: Decimal | None = None
    savings_amount: Decimal | None = None
    savings_percent: Decimal | None = None
    deal_url: str | None = None
    summary: str | None = None
    image_url: str | None = None
    detected_at: datetime
    published_at: datetime | None = None
    category: str | None = None
    subcategories: list[str] = Field(default_factory=list)
    personalization_score: float | None = None
    score_breakdown: DealScoreBreakdownResponse
    ai_copy_draft: AICopyDraftResponse | None = None


class PublishedDealFeedItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    currency: str
    current_price: Decimal
    previous_price: Decimal | None = None
    savings_percent: Decimal | None = None
    deal_url: str | None = None
    summary: str | None = None
    detected_at: datetime
    published_at: datetime | None = None
    category: str | None = None
    subcategories: list[str] = Field(default_factory=list)
    personalization_score: float | None = None


class PublishedDealsPageResponse(BaseModel):
    items: list[PublishedDealResponse] = Field(default_factory=list)
    next_cursor: str | None = None
    has_more: bool = False


class SavedDealItemResponse(BaseModel):
    saved_at: datetime
    deal: PublishedDealResponse


class DealPublicationResponse(BaseModel):
    deal_id: UUID
    deal_status: str
    published_at: datetime


class SourceMetricsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source_id: UUID
    source_slug: str
    source_name: str
    is_active: bool
    raw_ingestion_records_total: int
    raw_ingestion_records_accepted: int
    raw_ingestion_records_rejected: int
    raw_ingestion_records_duplicate: int = 0
    raw_ingestion_records_failed: int = 0
    deals_total: int
    deals_pending_review: int
    deals_approved: int
    deals_rejected: int
    deals_published: int = 0
    review_queue_pending: int


class MetricsOverviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    total_sources: int
    active_sources: int
    raw_ingestion_records_total: int
    raw_ingestion_records_recent: int
    raw_ingestion_records_accepted: int
    raw_ingestion_records_rejected: int
    raw_ingestion_records_duplicate: int = 0
    raw_ingestion_records_failed: int = 0
    deals_total: int
    deals_pending_review: int
    deals_approved: int
    deals_rejected: int
    deals_published: int = 0
    review_queue_pending: int
    breakdown_by_source: list[SourceMetricsResponse] = Field(default_factory=list)


class ProductAnalyticsDealPerformanceResponse(BaseModel):
    deal_id: UUID
    title: str
    category: str | None = None
    impression_count: int = 0
    click_count: int = 0
    save_count: int = 0
    unsave_count: int = 0
    recommended_impression_count: int = 0
    recommended_click_count: int = 0
    ctr: float = 0.0
    save_rate: float = 0.0
    recommended_ctr: float = 0.0


class ProductAnalyticsOverviewResponse(BaseModel):
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
    top_deals: list[ProductAnalyticsDealPerformanceResponse] = Field(default_factory=list)


class TrackedProductsSchedulerStatusResponse(BaseModel):
    enabled: bool
    is_running: bool
    interval_seconds: int | None = None
    last_started_at: datetime | None = None
    last_completed_at: datetime | None = None
    last_status: str
    last_error_reason: str | None = None
    tracked_asins: int | None = None
    eligible_asins: int | None = None
    fetched_products: int | None = None
    accepted: int | None = None
    rejected: int | None = None
    failed_batches: int | None = None
    skipped_reason: str | None = None


class TrackedProductsSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    total_tracked_products: int
    active_tracked_products: int
    never_attempted: int
    in_progress: int
    succeeded: int
    failed: int
    retry_backoff: int
    due_now: int


class TrackedProductItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    asin: str
    domain_id: int
    display_name: str | None = None
    source_slug: str | None = None
    source_name: str | None = None
    source_url: str | None = None
    is_active: bool
    last_refresh_attempt_at: datetime | None = None
    last_successful_refresh_at: datetime | None = None
    last_failed_refresh_at: datetime | None = None
    refresh_status: str
    refresh_failure_reason: str | None = None
    consecutive_refresh_failures: int = 0
    next_refresh_earliest_at: datetime | None = None
    refresh_priority: str
    staleness_classification: str
    observation_count_all_time: int = 0
    linked_deal_count: int = 0
    has_pending_review_deal: bool = False
    has_published_deal: bool = False


class TrackedProductsResponse(BaseModel):
    scheduler: TrackedProductsSchedulerStatusResponse
    summary: TrackedProductsSummaryResponse
    items: list[TrackedProductItemResponse] = Field(default_factory=list)


class DealsListItemResponse(BaseModel):
    """Lightweight response for the deals exploration card view."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    status: str
    currency: str
    current_price: Decimal
    previous_price: Decimal | None = None
    savings_amount: Decimal | None = None
    savings_percent: Decimal | None = None
    deal_url: str | None = None
    detected_at: datetime
    source_id: UUID
    source_category: str | None = None
    image_url: str | None = None
    quality_score: int | None = None
    business_score: int | None = None
    promotable: bool = False
    fake_discount: bool = False
    confidence_level: str | None = None
    quality_reasons: list[str] = Field(default_factory=list)
    price_history: DealPriceHistoryResponse | None = None
    asin: str | None = None


class DealsListPageResponse(BaseModel):
    items: list[DealsListItemResponse] = Field(default_factory=list)
    total: int = 0
    has_more: bool = False


class ReviewDecisionResponse(BaseModel):
    review_id: UUID
    review_status: str
    deal_id: UUID
    deal_status: str


class ReviewQueueListItemResponse(BaseModel):
    """Lightweight response for the approval queue card view.

    Omits ai_copy_draft, summary, subcategories, and variant hierarchy.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    priority: int
    created_at: datetime
    deal_id: UUID
    title: str
    currency: str
    current_price: Decimal
    previous_price: Decimal | None = None
    savings_amount: Decimal | None = None
    savings_percent: Decimal | None = None
    deal_url: str | None = None
    source_id: UUID
    source_category: str | None = None
    image_url: str | None = None
    quality_score: int | None = None
    business_score: int | None = None
    promotable: bool = False
    fake_discount: bool = False
    confidence_level: str | None = None
    quality_reasons: list[str] = Field(default_factory=list)
    price_history: DealPriceHistoryResponse | None = None
    asin: str | None = None


class ReviewQueuePageResponse(BaseModel):
    items: list[ReviewQueueListItemResponse] = Field(default_factory=list)
    total: int = 0
    has_more: bool = False


class ReviewQueueItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: str
    reason: str
    priority: int
    created_at: datetime
    resolved_at: datetime | None = None
    deal: DealResponse


class IngestRunRequest(BaseModel):
    source_slug: str
    parser: str
    payload: dict[str, Any] | list[dict[str, Any]] | str

    @field_validator("source_slug", "parser")
    @classmethod
    def validate_identifier(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("field is required")
        if len(cleaned) > 100:
            raise ValueError("field is too long")
        return cleaned

    @model_validator(mode="after")
    def validate_payload(self) -> "IngestRunRequest":
        if isinstance(self.payload, str):
            if not self.payload.strip():
                raise ValueError("payload must not be empty")
            if len(self.payload.encode("utf-8")) > 5_000_000:
                raise ValueError("payload is too large")
        elif isinstance(self.payload, list):
            if not self.payload:
                raise ValueError("payload must not be empty")
            if len(self.payload) > 5_000:
                raise ValueError("payload has too many records")
        elif isinstance(self.payload, dict):
            if not self.payload:
                raise ValueError("payload must not be empty")
        return self


class IngestionRecordResponse(BaseModel):
    raw_ingestion_record_id: str
    product_source_record_id: str | None = None
    price_observation_id: str | None = None
    status: str
    rejection_reason: str | None = None


class IngestRunResponse(BaseModel):
    source_slug: str
    parser_name: str
    processed: int
    accepted: int
    rejected: int
    skipped_due_to_dedupe: int = 0
    records: list[IngestionRecordResponse]
