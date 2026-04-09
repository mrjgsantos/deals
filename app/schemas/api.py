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
    score_breakdown: DealScoreBreakdownResponse
    ai_copy_draft: AICopyDraftResponse | None = None


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
