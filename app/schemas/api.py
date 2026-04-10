from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class HealthResponse(BaseModel):
    status: str


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
    detected_at: datetime
    published_at: datetime | None = None
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


class ReviewDecisionResponse(BaseModel):
    review_id: UUID
    review_status: str
    deal_id: UUID
    deal_status: str


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
    records: list[IngestionRecordResponse]
