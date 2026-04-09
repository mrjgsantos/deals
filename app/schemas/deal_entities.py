from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import Field

from app.db.enums import (
    AICopyDraftStatus,
    AICopyType,
    AvailabilityStatus,
    DealStatus,
    PriceStatisticWindow,
    ReviewStatus,
    ReviewType,
    SourceType,
)
from app.schemas.common import ORMBaseSchema


class SourceBase(ORMBaseSchema):
    name: str
    slug: str
    source_type: SourceType
    base_url: str | None = None
    is_active: bool = True
    config: dict = Field(default_factory=dict)


class SourceCreate(SourceBase):
    pass


class SourceRead(SourceBase):
    id: UUID
    created_at: datetime
    updated_at: datetime


class MerchantBase(ORMBaseSchema):
    canonical_name: str
    slug: str
    website_url: str | None = None
    country_code: str | None = None
    is_active: bool = True
    metadata_json: dict = Field(default_factory=dict)


class MerchantCreate(MerchantBase):
    pass


class MerchantRead(MerchantBase):
    id: UUID
    created_at: datetime
    updated_at: datetime


class ProductBase(ORMBaseSchema):
    merchant_id: UUID | None = None
    normalized_name: str
    brand: str | None = None
    category: str | None = None
    description: str | None = None
    metadata_json: dict = Field(default_factory=dict)
    is_active: bool = True


class ProductCreate(ProductBase):
    pass


class ProductRead(ProductBase):
    id: UUID
    created_at: datetime
    updated_at: datetime


class ProductVariantBase(ORMBaseSchema):
    product_id: UUID
    variant_key: str
    sku: str | None = None
    gtin: str | None = None
    mpn: str | None = None
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
    metadata_json: dict = Field(default_factory=dict)
    is_active: bool = True


class ProductVariantCreate(ProductVariantBase):
    pass


class ProductVariantRead(ProductVariantBase):
    id: UUID
    created_at: datetime
    updated_at: datetime


class ProductSourceRecordBase(ORMBaseSchema):
    source_id: UUID
    merchant_id: UUID | None = None
    product_id: UUID | None = None
    product_variant_id: UUID | None = None
    external_id: str
    source_url: str | None = None
    image_url: str | None = None
    source_title: str
    source_brand: str | None = None
    source_description: str | None = None
    source_category: str | None = None
    currency: str
    availability_status: AvailabilityStatus = AvailabilityStatus.UNKNOWN
    source_attributes: dict = Field(default_factory=dict)
    raw_payload: dict = Field(default_factory=dict)


class ProductSourceRecordCreate(ProductSourceRecordBase):
    pass


class ProductSourceRecordRead(ProductSourceRecordBase):
    id: UUID
    first_seen_at: datetime
    last_seen_at: datetime
    matched_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class PriceObservationBase(ORMBaseSchema):
    product_source_record_id: UUID
    currency: str
    list_price: Decimal | None = None
    sale_price: Decimal | None = None
    shipping_price: Decimal | None = None
    total_price: Decimal | None = None
    in_stock: bool | None = None
    is_promotional: bool = False
    observed_hash: str | None = None
    metadata_json: dict = Field(default_factory=dict)


class PriceObservationCreate(PriceObservationBase):
    observed_at: datetime | None = None


class PriceObservationRead(PriceObservationBase):
    id: UUID
    observed_at: datetime


class PriceStatisticBase(ORMBaseSchema):
    product_variant_id: UUID
    source_id: UUID
    statistic_window: PriceStatisticWindow
    observed_on: date
    currency: str
    sample_count: int = 1
    min_price: Decimal | None = None
    max_price: Decimal | None = None
    avg_price: Decimal | None = None
    median_price: Decimal | None = None
    last_price: Decimal | None = None


class PriceStatisticCreate(PriceStatisticBase):
    pass


class PriceStatisticRead(PriceStatisticBase):
    id: UUID
    created_at: datetime
    updated_at: datetime


class DealBase(ORMBaseSchema):
    product_variant_id: UUID | None = None
    product_source_record_id: UUID | None = None
    price_observation_id: UUID | None = None
    source_id: UUID
    title: str
    status: DealStatus = DealStatus.CANDIDATE
    currency: str
    current_price: Decimal
    previous_price: Decimal | None = None
    savings_amount: Decimal | None = None
    savings_percent: Decimal | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    deal_url: str | None = None
    summary: str | None = None
    is_featured: bool = False
    metadata_json: dict = Field(default_factory=dict)


class DealCreate(DealBase):
    pass


class DealRead(DealBase):
    id: UUID
    detected_at: datetime
    created_at: datetime
    updated_at: datetime


class ReviewQueueBase(ORMBaseSchema):
    product_source_record_id: UUID | None = None
    entity_type: ReviewType
    entity_id: UUID
    status: ReviewStatus = ReviewStatus.PENDING
    priority: int = 100
    reason: str
    payload: dict = Field(default_factory=dict)
    assigned_to: str | None = None


class ReviewQueueCreate(ReviewQueueBase):
    pass


class ReviewQueueRead(ReviewQueueBase):
    id: UUID
    resolved_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class AICopyDraftBase(ORMBaseSchema):
    deal_id: UUID
    copy_type: AICopyType
    status: AICopyDraftStatus = AICopyDraftStatus.DRAFT
    model_name: str | None = None
    prompt_version: str | None = None
    content: str
    metadata_json: dict = Field(default_factory=dict)


class AICopyDraftCreate(AICopyDraftBase):
    pass


class AICopyDraftRead(AICopyDraftBase):
    id: UUID
    generated_at: datetime
    approved_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
