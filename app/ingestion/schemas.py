from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

from app.db.enums import AvailabilityStatus


class ParsedSourceRecord(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    external_id: str
    product_url: str | None = None
    title: str | None = None
    brand: str | None = None
    category: str | None = None
    description: str | None = None
    image_url: str | None = None
    merchant_name: str | None = None
    currency: str | None = None
    current_price: Decimal | None = None
    list_price: Decimal | None = None
    shipping_price: Decimal | None = None
    availability_status: AvailabilityStatus = AvailabilityStatus.UNKNOWN
    pack_count: int | None = None
    quantity: Decimal | None = None
    quantity_unit: str | None = None
    weight: Decimal | None = None
    weight_unit: str | None = None
    volume: Decimal | None = None
    volume_unit: str | None = None
    size: str | None = None
    color: str | None = None
    material: str | None = None
    is_bundle: bool = False
    observed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source_attributes: dict[str, Any] = Field(default_factory=dict)
    raw_payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("external_id")
    @classmethod
    def validate_external_id(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("external_id is required")
        if len(cleaned) > 255:
            raise ValueError("external_id is too long")
        return cleaned


class NormalizedIngestionRecord(BaseModel):
    normalized_name: str
    variant_key: str
    product_url: HttpUrl
    external_id: str
    brand: str | None = None
    category: str | None = None
    description: str | None = None
    image_url: str | None = None
    merchant_name: str | None = None
    merchant_slug: str | None = None
    currency: str
    current_price: Decimal
    list_price: Decimal | None = None
    shipping_price: Decimal | None = None
    total_price: Decimal
    availability_status: AvailabilityStatus
    source_title: str
    source_brand: str | None = None
    source_description: str | None = None
    source_category: str | None = None
    source_attributes: dict[str, Any] = Field(default_factory=dict)
    raw_payload: dict[str, Any] = Field(default_factory=dict)
    observed_at: datetime
    pack_count: int | None = None
    quantity: Decimal | None = None
    quantity_unit: str | None = None
    weight: Decimal | None = None
    weight_unit: str | None = None
    volume: Decimal | None = None
    volume_unit: str | None = None
    size: str | None = None
    color: str | None = None
    material: str | None = None
    is_bundle: bool = False

    @field_validator("external_id", "variant_key", "normalized_name", "source_title", "currency")
    @classmethod
    def validate_required_strings(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("required string field is empty")
        return cleaned


class IngestionRecordResult(BaseModel):
    raw_ingestion_record_id: str
    product_source_record_id: str | None = None
    price_observation_id: str | None = None
    status: str
    rejection_reason: str | None = None


class IngestionBatchResult(BaseModel):
    source_slug: str
    parser_name: str
    processed: int = 0
    accepted: int = 0
    rejected: int = 0
    skipped_due_to_dedupe: int = 0
    records: list[IngestionRecordResult] = Field(default_factory=list)
