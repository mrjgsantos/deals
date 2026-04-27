from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
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

ENUM_VALUES = lambda enum_cls: [member.value for member in enum_cls]


class Source(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "sources"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_sources_slug"),
        Index("ix_sources_source_type_is_active", "source_type", "is_active"),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False)
    source_type: Mapped[SourceType] = mapped_column(
        Enum(SourceType, name="source_type_enum", values_callable=ENUM_VALUES),
        nullable=False,
    )
    base_url: Mapped[str | None] = mapped_column(String(500))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    config: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )

    product_source_records: Mapped[list[ProductSourceRecord]] = relationship(back_populates="source")
    raw_ingestion_records: Mapped[list[RawIngestionRecord]] = relationship(back_populates="source")
    price_statistics: Mapped[list[PriceStatistic]] = relationship(back_populates="source")
    deals: Mapped[list[Deal]] = relationship(back_populates="source")
    asin_ingestion_checkpoints: Mapped[list[AsinIngestionCheckpoint]] = relationship(back_populates="source")


class TrackedProduct(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "tracked_products"
    __table_args__ = (
        UniqueConstraint("asin", "domain_id", name="uq_tracked_products_asin_domain"),
        Index("ix_tracked_products_last_checked_at", "last_checked_at"),
        Index("ix_tracked_products_next_refresh_eligible_at", "next_refresh_eligible_at"),
    )

    asin: Mapped[str] = mapped_column(String(16), nullable=False)
    domain_id: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_refresh_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_refresh_succeeded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_refresh_failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_refresh_status: Mapped[str | None] = mapped_column(String(32))
    last_refresh_failure_reason: Mapped[str | None] = mapped_column(String(255))
    consecutive_refresh_failures: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    next_refresh_eligible_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AsinIngestionCheckpoint(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "asin_ingestion_checkpoints"
    __table_args__ = (
        UniqueConstraint("source_id", "asin", name="uq_asin_ingestion_checkpoints_source_asin"),
        Index("ix_asin_ingestion_checkpoints_source_id_last_processed_at", "source_id", "last_processed_at"),
    )

    source_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("sources.id", ondelete="CASCADE"),
        nullable=False,
    )
    asin: Mapped[str] = mapped_column(String(16), nullable=False)
    last_processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    source: Mapped[Source] = relationship(back_populates="asin_ingestion_checkpoints")


class User(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("email", name="uq_users_email"),
        UniqueConstraint("google_sub", name="uq_users_google_sub"),
        Index("ix_users_email", "email"),
        Index("ix_users_google_sub", "google_sub"),
    )

    email: Mapped[str] = mapped_column(String(320), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    google_sub: Mapped[str | None] = mapped_column(String(255))
    display_name: Mapped[str | None] = mapped_column(String(255))
    avatar_url: Mapped[str | None] = mapped_column(String(1000))
    is_staff: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_deals_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    saved_deals: Mapped[list[SavedDeal]] = relationship(back_populates="user", cascade="all, delete-orphan")
    category_signals: Mapped[list[UserCategorySignal]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    events: Mapped[list[UserEvent]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    preferences: Mapped[UserPreference | None] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        uselist=False,
    )


class Merchant(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "merchants"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_merchants_slug"),
        Index("ix_merchants_canonical_name", "canonical_name"),
        Index("ix_merchants_country_code", "country_code"),
    )

    canonical_name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), nullable=False)
    website_url: Mapped[str | None] = mapped_column(String(500))
    country_code: Mapped[str | None] = mapped_column(String(2))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    metadata_json: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )

    products: Mapped[list[Product]] = relationship(back_populates="merchant")
    product_source_records: Mapped[list[ProductSourceRecord]] = relationship(back_populates="merchant")


class Product(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "products"
    __table_args__ = (
        Index("ix_products_merchant_id", "merchant_id"),
        Index("ix_products_normalized_name", "normalized_name"),
        Index("ix_products_brand", "brand"),
    )

    merchant_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("merchants.id", ondelete="SET NULL"),
        nullable=True,
    )
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False)
    brand: Mapped[str | None] = mapped_column(String(255))
    category: Mapped[str | None] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))

    merchant: Mapped[Merchant | None] = relationship(back_populates="products")
    variants: Mapped[list[ProductVariant]] = relationship(back_populates="product")
    source_records: Mapped[list[ProductSourceRecord]] = relationship(back_populates="product")


class ProductVariant(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "product_variants"
    __table_args__ = (
        UniqueConstraint("product_id", "variant_key", name="uq_product_variants_product_variant_key"),
        Index("ix_product_variants_product_id", "product_id"),
        Index("ix_product_variants_sku", "sku"),
        Index("ix_product_variants_gtin", "gtin"),
        CheckConstraint("pack_count IS NULL OR pack_count >= 0", name="ck_product_variants_pack_count_non_negative"),
        CheckConstraint("quantity IS NULL OR quantity >= 0", name="ck_product_variants_quantity_non_negative"),
        CheckConstraint("weight IS NULL OR weight >= 0", name="ck_product_variants_weight_non_negative"),
        CheckConstraint("volume IS NULL OR volume >= 0", name="ck_product_variants_volume_non_negative"),
    )

    product_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
    )
    variant_key: Mapped[str] = mapped_column(String(255), nullable=False)
    sku: Mapped[str | None] = mapped_column(String(120))
    gtin: Mapped[str | None] = mapped_column(String(32))
    mpn: Mapped[str | None] = mapped_column(String(120))
    pack_count: Mapped[int | None] = mapped_column(Integer)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    quantity_unit: Mapped[str | None] = mapped_column(String(32))
    weight: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    weight_unit: Mapped[str | None] = mapped_column(String(32))
    volume: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    volume_unit: Mapped[str | None] = mapped_column(String(32))
    size: Mapped[str | None] = mapped_column(String(64))
    color: Mapped[str | None] = mapped_column(String(64))
    material: Mapped[str | None] = mapped_column(String(128))
    is_bundle: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    metadata_json: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))

    product: Mapped[Product] = relationship(back_populates="variants")
    source_records: Mapped[list[ProductSourceRecord]] = relationship(back_populates="product_variant")
    price_statistics: Mapped[list[PriceStatistic]] = relationship(back_populates="product_variant")
    deals: Mapped[list[Deal]] = relationship(back_populates="product_variant")


class ProductSourceRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "product_source_records"
    __table_args__ = (
        UniqueConstraint("source_id", "external_id", name="uq_product_source_records_source_external"),
        Index("ix_product_source_records_source_id_last_seen_at", "source_id", "last_seen_at"),
        Index("ix_product_source_records_product_variant_id", "product_variant_id"),
        Index("ix_product_source_records_product_id", "product_id"),
        Index("ix_product_source_records_merchant_id", "merchant_id"),
        Index("ix_product_source_records_availability_status", "availability_status"),
    )

    source_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("sources.id", ondelete="CASCADE"),
        nullable=False,
    )
    merchant_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("merchants.id", ondelete="SET NULL"),
        nullable=True,
    )
    product_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("products.id", ondelete="SET NULL"),
        nullable=True,
    )
    product_variant_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("product_variants.id", ondelete="SET NULL"),
        nullable=True,
    )
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(1000))
    image_url: Mapped[str | None] = mapped_column(String(1000))
    source_title: Mapped[str] = mapped_column(String(500), nullable=False)
    source_brand: Mapped[str | None] = mapped_column(String(255))
    source_description: Mapped[str | None] = mapped_column(Text)
    source_category: Mapped[str | None] = mapped_column(String(255))
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    availability_status: Mapped[AvailabilityStatus] = mapped_column(
        Enum(AvailabilityStatus, name="availability_status_enum", values_callable=ENUM_VALUES),
        nullable=False,
        default=AvailabilityStatus.UNKNOWN,
        server_default=text(f"'{AvailabilityStatus.UNKNOWN.value}'"),
    )
    source_attributes: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    raw_payload: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    matched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    source: Mapped[Source] = relationship(back_populates="product_source_records")
    merchant: Mapped[Merchant | None] = relationship(back_populates="product_source_records")
    product: Mapped[Product | None] = relationship(back_populates="source_records")
    product_variant: Mapped[ProductVariant | None] = relationship(back_populates="source_records")
    raw_ingestion_records: Mapped[list[RawIngestionRecord]] = relationship(back_populates="product_source_record")
    price_observations: Mapped[list[PriceObservation]] = relationship(back_populates="product_source_record")
    review_queue_items: Mapped[list[ReviewQueue]] = relationship(back_populates="product_source_record")
    deals: Mapped[list[Deal]] = relationship(back_populates="product_source_record")


class RawIngestionRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "raw_ingestion_records"
    __table_args__ = (
        Index("ix_raw_ingestion_records_source_id_processed_at", "source_id", "processed_at"),
        Index("ix_raw_ingestion_records_status", "status"),
        Index("ix_raw_ingestion_records_product_source_record_id", "product_source_record_id"),
    )

    source_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("sources.id", ondelete="CASCADE"),
        nullable=False,
    )
    product_source_record_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("product_source_records.id", ondelete="SET NULL"),
        nullable=True,
    )
    parser_name: Mapped[str] = mapped_column(String(100), nullable=False)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", server_default=text("'pending'"))
    rejection_reason: Mapped[str | None] = mapped_column(String(255))
    raw_payload: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    normalized_payload: Mapped[dict | None] = mapped_column(JSONB)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    source: Mapped[Source] = relationship(back_populates="raw_ingestion_records")
    product_source_record: Mapped[ProductSourceRecord | None] = relationship(back_populates="raw_ingestion_records")


class PriceObservation(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "price_observations"
    __table_args__ = (
        Index("ix_price_observations_record_id_observed_at", "product_source_record_id", "observed_at"),
        Index("ix_price_observations_total_price", "total_price"),
        Index("ix_price_observations_sale_price", "sale_price"),
        Index(
            "uq_price_observations_record_id_observed_hash",
            "product_source_record_id",
            "observed_hash",
            unique=True,
        ),
    )

    product_source_record_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("product_source_records.id", ondelete="CASCADE"),
        nullable=False,
    )
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    list_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    sale_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    shipping_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    total_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    in_stock: Mapped[bool | None] = mapped_column(Boolean)
    is_promotional: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    observed_hash: Mapped[str | None] = mapped_column(String(128))
    metadata_json: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )

    product_source_record: Mapped[ProductSourceRecord] = relationship(back_populates="price_observations")
    deals: Mapped[list[Deal]] = relationship(back_populates="price_observation")


class PriceStatistic(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "price_statistics"
    __table_args__ = (
        UniqueConstraint(
            "product_variant_id",
            "source_id",
            "statistic_window",
            "observed_on",
            name="uq_price_statistics_variant_source_window_observed_on",
        ),
        Index("ix_price_statistics_variant_window", "product_variant_id", "statistic_window"),
        Index("ix_price_statistics_source_observed_on", "source_id", "observed_on"),
    )

    product_variant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("product_variants.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("sources.id", ondelete="CASCADE"),
        nullable=False,
    )
    statistic_window: Mapped[PriceStatisticWindow] = mapped_column(
        Enum(PriceStatisticWindow, name="price_statistic_window_enum", values_callable=ENUM_VALUES),
        nullable=False,
    )
    observed_on: Mapped[date] = mapped_column(Date, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default=text("1"))
    min_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    max_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    avg_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    median_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    last_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    metadata_json: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )

    product_variant: Mapped[ProductVariant] = relationship(back_populates="price_statistics")
    source: Mapped[Source] = relationship(back_populates="price_statistics")


class Deal(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "deals"
    __table_args__ = (
        Index("ix_deals_status_starts_at", "status", "starts_at"),
        Index("ix_deals_product_variant_id", "product_variant_id"),
        Index("ix_deals_source_id_detected_at", "source_id", "detected_at"),
        Index("ix_deals_ends_at", "ends_at"),
        Index(
            "ix_deals_status_published_at",
            "status",
            text("published_at DESC"),
            postgresql_where=text("published_at IS NOT NULL"),
        ),
    )

    product_variant_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("product_variants.id", ondelete="SET NULL"),
        nullable=True,
    )
    product_source_record_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("product_source_records.id", ondelete="SET NULL"),
        nullable=True,
    )
    price_observation_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("price_observations.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("sources.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[DealStatus] = mapped_column(
        Enum(DealStatus, name="deal_status_enum", values_callable=ENUM_VALUES),
        nullable=False,
        default=DealStatus.PENDING_REVIEW,
        server_default=text(f"'{DealStatus.PENDING_REVIEW.value}'"),
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    current_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    previous_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    savings_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    savings_percent: Mapped[Decimal | None] = mapped_column(Numeric(7, 4))
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    deal_url: Mapped[str | None] = mapped_column(String(1000))
    summary: Mapped[str | None] = mapped_column(Text)
    is_featured: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    metadata_json: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )

    product_variant: Mapped[ProductVariant | None] = relationship(back_populates="deals")
    product_source_record: Mapped[ProductSourceRecord | None] = relationship(back_populates="deals")
    price_observation: Mapped[PriceObservation | None] = relationship(back_populates="deals")
    source: Mapped[Source] = relationship(back_populates="deals")
    ai_copy_drafts: Mapped[list[AICopyDraft]] = relationship(back_populates="deal")
    saved_deals: Mapped[list[SavedDeal]] = relationship(back_populates="deal", cascade="all, delete-orphan")


class SavedDeal(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "saved_deals"
    __table_args__ = (
        UniqueConstraint("user_id", "deal_id", name="uq_saved_deals_user_deal"),
        Index("ix_saved_deals_user_id_created_at", "user_id", "created_at"),
        Index("ix_saved_deals_deal_id", "deal_id"),
    )

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    deal_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("deals.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    user: Mapped[User] = relationship(back_populates="saved_deals")
    deal: Mapped[Deal] = relationship(back_populates="saved_deals")


class UserPreference(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "user_preferences"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_user_preferences_user_id"),
    )

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    categories: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    budget_preference: Mapped[str | None] = mapped_column(String(16))
    intent: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default=text("'[]'::jsonb"),
    )
    has_pets: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    has_kids: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
    context_flags: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    user: Mapped[User] = relationship(back_populates="preferences")


class UserCategorySignal(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "user_category_signals"
    __table_args__ = (
        UniqueConstraint("user_id", "category", name="uq_user_category_signals_user_category"),
        Index("ix_user_category_signals_user_id_affinity_score", "user_id", "affinity_score"),
        Index("ix_user_category_signals_user_id_updated_at", "user_id", "updated_at"),
    )

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    affinity_score: Mapped[Decimal] = mapped_column(
        Numeric(8, 4),
        nullable=False,
        default=Decimal("0"),
        server_default=text("0"),
    )
    saved_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    clicked_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    negative_affinity: Mapped[Decimal] = mapped_column(
        Numeric(8, 4),
        nullable=False,
        default=Decimal("0"),
        server_default=text("0"),
    )
    last_interacted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="category_signals")


class UserEvent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "user_events"
    __table_args__ = (
        Index("ix_user_events_user_id_created_at", "user_id", "created_at"),
        Index("ix_user_events_event_type_created_at", "event_type", "created_at"),
        Index("ix_user_events_deal_id_event_type", "deal_id", "event_type"),
    )

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    deal_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("deals.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    user: Mapped[User] = relationship(back_populates="events")
    deal: Mapped[Deal | None] = relationship()


class ReviewQueue(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "review_queue"
    __table_args__ = (
        Index("ix_review_queue_status_priority", "status", "priority"),
        Index("ix_review_queue_entity_type_entity_id", "entity_type", "entity_id"),
        Index("ix_review_queue_product_source_record_id", "product_source_record_id"),
    )

    product_source_record_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("product_source_records.id", ondelete="SET NULL"),
        nullable=True,
    )
    entity_type: Mapped[ReviewType] = mapped_column(
        Enum(ReviewType, name="review_type_enum", values_callable=ENUM_VALUES),
        nullable=False,
    )
    entity_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    status: Mapped[ReviewStatus] = mapped_column(
        Enum(ReviewStatus, name="review_status_enum", values_callable=ENUM_VALUES),
        nullable=False,
        default=ReviewStatus.PENDING,
        server_default=text(f"'{ReviewStatus.PENDING.value}'"),
    )
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100, server_default=text("100"))
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    payload: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    assigned_to: Mapped[str | None] = mapped_column(String(255))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    product_source_record: Mapped[ProductSourceRecord | None] = relationship(back_populates="review_queue_items")


class AICopyDraft(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "ai_copy_drafts"
    __table_args__ = (
        Index("ix_ai_copy_drafts_deal_id_status", "deal_id", "status"),
        Index("ix_ai_copy_drafts_copy_type", "copy_type"),
        Index("ix_ai_copy_drafts_deal_id_generated_at", "deal_id", text("generated_at DESC")),
    )

    deal_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("deals.id", ondelete="CASCADE"),
        nullable=False,
    )
    copy_type: Mapped[AICopyType] = mapped_column(
        Enum(AICopyType, name="ai_copy_type_enum", values_callable=ENUM_VALUES),
        nullable=False,
    )
    status: Mapped[AICopyDraftStatus] = mapped_column(
        Enum(AICopyDraftStatus, name="ai_copy_draft_status_enum", values_callable=ENUM_VALUES),
        nullable=False,
        default=AICopyDraftStatus.DRAFT,
        server_default=text(f"'{AICopyDraftStatus.DRAFT.value}'"),
    )
    model_name: Mapped[str | None] = mapped_column(String(120))
    prompt_version: Mapped[str | None] = mapped_column(String(64))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    deal: Mapped[Deal] = relationship(back_populates="ai_copy_drafts")


class ScoringKeyword(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Configurable keyword lists used by the deal scoring engine.

    list_name values:
      - 'high_demand'        : category/title keywords that boost score
      - 'recognized_brand'   : brand keywords that boost score
      - 'low_signal_keyword' : title keywords that disqualify a deal
      - 'low_signal_category': source_category values that disqualify a deal
    """

    __tablename__ = "scoring_keywords"
    __table_args__ = (
        UniqueConstraint("list_name", "keyword", name="uq_scoring_keywords_list_keyword"),
        Index("ix_scoring_keywords_list_name", "list_name"),
    )

    list_name: Mapped[str] = mapped_column(String(64), nullable=False)
    keyword: Mapped[str] = mapped_column(String(255), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))


class EmailVerificationToken(UUIDPrimaryKeyMixin, Base):
    """Single-use tokens for verifying a user's email address."""

    __tablename__ = "email_verification_tokens"
    __table_args__ = (Index("ix_email_verification_tokens_token_hash", "token_hash"),)

    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    user: Mapped[User] = relationship()


class PasswordResetToken(UUIDPrimaryKeyMixin, Base):
    """Single-use tokens for password reset flow.

    The plain token is sent by email; only the SHA-256 hash is stored.
    """

    __tablename__ = "password_reset_tokens"
    __table_args__ = (Index("ix_password_reset_tokens_token_hash", "token_hash"),)

    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    user: Mapped[User] = relationship()
