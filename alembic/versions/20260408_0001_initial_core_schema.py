"""initial core schema

Revision ID: 20260408_0001
Revises:
Create Date: 2026-04-08 21:15:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "20260408_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


source_type_enum = postgresql.ENUM(
    "website",
    "affiliate_feed",
    "merchant_api",
    "marketplace",
    "manual",
    name="source_type_enum",
    create_type=False,
)
availability_status_enum = postgresql.ENUM(
    "in_stock",
    "out_of_stock",
    "preorder",
    "unknown",
    name="availability_status_enum",
    create_type=False,
)
price_statistic_window_enum = postgresql.ENUM(
    "daily",
    "weekly",
    "monthly",
    name="price_statistic_window_enum",
    create_type=False,
)
deal_status_enum = postgresql.ENUM(
    "candidate",
    "active",
    "expired",
    "rejected",
    name="deal_status_enum",
    create_type=False,
)
review_status_enum = postgresql.ENUM(
    "pending",
    "in_review",
    "resolved",
    "dismissed",
    name="review_status_enum",
    create_type=False,
)
review_type_enum = postgresql.ENUM(
    "merchant_match",
    "product_match",
    "variant_match",
    "deal_validation",
    "copy_review",
    name="review_type_enum",
    create_type=False,
)
ai_copy_type_enum = postgresql.ENUM(
    "headline",
    "body",
    "short_description",
    "disclaimer",
    name="ai_copy_type_enum",
    create_type=False,
)
ai_copy_draft_status_enum = postgresql.ENUM(
    "draft",
    "approved",
    "rejected",
    name="ai_copy_draft_status_enum",
    create_type=False,
)


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto";')

    bind = op.get_bind()
    source_type_enum.create(bind, checkfirst=True)
    availability_status_enum.create(bind, checkfirst=True)
    price_statistic_window_enum.create(bind, checkfirst=True)
    deal_status_enum.create(bind, checkfirst=True)
    review_status_enum.create(bind, checkfirst=True)
    review_type_enum.create(bind, checkfirst=True)
    ai_copy_type_enum.create(bind, checkfirst=True)
    ai_copy_draft_status_enum.create(bind, checkfirst=True)

    op.create_table(
        "sources",
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("source_type", source_type_enum, nullable=False),
        sa.Column("base_url", sa.String(length=500), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_sources_slug"),
    )
    op.create_index("ix_sources_source_type_is_active", "sources", ["source_type", "is_active"], unique=False)

    op.create_table(
        "merchants",
        sa.Column("canonical_name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("website_url", sa.String(length=500), nullable=True),
        sa.Column("country_code", sa.String(length=2), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_merchants_slug"),
    )
    op.create_index("ix_merchants_canonical_name", "merchants", ["canonical_name"], unique=False)
    op.create_index("ix_merchants_country_code", "merchants", ["country_code"], unique=False)

    op.create_table(
        "products",
        sa.Column("merchant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("normalized_name", sa.String(length=255), nullable=False),
        sa.Column("brand", sa.String(length=255), nullable=True),
        sa.Column("category", sa.String(length=120), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["merchant_id"], ["merchants.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_products_brand", "products", ["brand"], unique=False)
    op.create_index("ix_products_merchant_id", "products", ["merchant_id"], unique=False)
    op.create_index("ix_products_normalized_name", "products", ["normalized_name"], unique=False)

    op.create_table(
        "product_variants",
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("variant_key", sa.String(length=255), nullable=False),
        sa.Column("sku", sa.String(length=120), nullable=True),
        sa.Column("gtin", sa.String(length=32), nullable=True),
        sa.Column("mpn", sa.String(length=120), nullable=True),
        sa.Column("pack_count", sa.Integer(), nullable=True),
        sa.Column("quantity", sa.Numeric(precision=12, scale=3), nullable=True),
        sa.Column("quantity_unit", sa.String(length=32), nullable=True),
        sa.Column("weight", sa.Numeric(precision=12, scale=3), nullable=True),
        sa.Column("weight_unit", sa.String(length=32), nullable=True),
        sa.Column("volume", sa.Numeric(precision=12, scale=3), nullable=True),
        sa.Column("volume_unit", sa.String(length=32), nullable=True),
        sa.Column("size", sa.String(length=64), nullable=True),
        sa.Column("color", sa.String(length=64), nullable=True),
        sa.Column("material", sa.String(length=128), nullable=True),
        sa.Column("is_bundle", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("pack_count IS NULL OR pack_count >= 0", name="ck_product_variants_pack_count_non_negative"),
        sa.CheckConstraint("quantity IS NULL OR quantity >= 0", name="ck_product_variants_quantity_non_negative"),
        sa.CheckConstraint("volume IS NULL OR volume >= 0", name="ck_product_variants_volume_non_negative"),
        sa.CheckConstraint("weight IS NULL OR weight >= 0", name="ck_product_variants_weight_non_negative"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("product_id", "variant_key", name="uq_product_variants_product_variant_key"),
    )
    op.create_index("ix_product_variants_gtin", "product_variants", ["gtin"], unique=False)
    op.create_index("ix_product_variants_product_id", "product_variants", ["product_id"], unique=False)
    op.create_index("ix_product_variants_sku", "product_variants", ["sku"], unique=False)

    op.create_table(
        "product_source_records",
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("merchant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("product_variant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("source_url", sa.String(length=1000), nullable=True),
        sa.Column("image_url", sa.String(length=1000), nullable=True),
        sa.Column("source_title", sa.String(length=500), nullable=False),
        sa.Column("source_brand", sa.String(length=255), nullable=True),
        sa.Column("source_description", sa.Text(), nullable=True),
        sa.Column("source_category", sa.String(length=255), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("availability_status", availability_status_enum, server_default="unknown", nullable=False),
        sa.Column("source_attributes", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("matched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["merchant_id"], ["merchants.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["product_variant_id"], ["product_variants.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_id", "external_id", name="uq_product_source_records_source_external"),
    )
    op.create_index("ix_product_source_records_availability_status", "product_source_records", ["availability_status"], unique=False)
    op.create_index("ix_product_source_records_merchant_id", "product_source_records", ["merchant_id"], unique=False)
    op.create_index("ix_product_source_records_product_id", "product_source_records", ["product_id"], unique=False)
    op.create_index("ix_product_source_records_product_variant_id", "product_source_records", ["product_variant_id"], unique=False)
    op.create_index("ix_product_source_records_source_id_last_seen_at", "product_source_records", ["source_id", "last_seen_at"], unique=False)

    op.create_table(
        "price_observations",
        sa.Column("product_source_record_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("list_price", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("sale_price", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("shipping_price", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("total_price", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("in_stock", sa.Boolean(), nullable=True),
        sa.Column("is_promotional", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("observed_hash", sa.String(length=128), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["product_source_record_id"], ["product_source_records.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_price_observations_record_id_observed_at", "price_observations", ["product_source_record_id", "observed_at"], unique=False)
    op.create_index("ix_price_observations_sale_price", "price_observations", ["sale_price"], unique=False)
    op.create_index("ix_price_observations_total_price", "price_observations", ["total_price"], unique=False)

    op.create_table(
        "price_statistics",
        sa.Column("product_variant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("statistic_window", price_statistic_window_enum, nullable=False),
        sa.Column("observed_on", sa.Date(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("sample_count", sa.Integer(), server_default="1", nullable=False),
        sa.Column("min_price", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("max_price", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("avg_price", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("median_price", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("last_price", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["product_variant_id"], ["product_variants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("product_variant_id", "source_id", "statistic_window", "observed_on", name="uq_price_statistics_variant_source_window_observed_on"),
    )
    op.create_index("ix_price_statistics_source_observed_on", "price_statistics", ["source_id", "observed_on"], unique=False)
    op.create_index("ix_price_statistics_variant_window", "price_statistics", ["product_variant_id", "statistic_window"], unique=False)

    op.create_table(
        "deals",
        sa.Column("product_variant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("product_source_record_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("price_observation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("status", deal_status_enum, server_default="candidate", nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("current_price", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("previous_price", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("savings_amount", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("savings_percent", sa.Numeric(precision=7, scale=4), nullable=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("detected_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deal_url", sa.String(length=1000), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("is_featured", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["price_observation_id"], ["price_observations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["product_source_record_id"], ["product_source_records.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["product_variant_id"], ["product_variants.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_deals_ends_at", "deals", ["ends_at"], unique=False)
    op.create_index("ix_deals_product_variant_id", "deals", ["product_variant_id"], unique=False)
    op.create_index("ix_deals_source_id_detected_at", "deals", ["source_id", "detected_at"], unique=False)
    op.create_index("ix_deals_status_starts_at", "deals", ["status", "starts_at"], unique=False)

    op.create_table(
        "review_queue",
        sa.Column("product_source_record_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("entity_type", review_type_enum, nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", review_status_enum, server_default="pending", nullable=False),
        sa.Column("priority", sa.Integer(), server_default="100", nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("assigned_to", sa.String(length=255), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["product_source_record_id"], ["product_source_records.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_review_queue_entity_type_entity_id", "review_queue", ["entity_type", "entity_id"], unique=False)
    op.create_index("ix_review_queue_product_source_record_id", "review_queue", ["product_source_record_id"], unique=False)
    op.create_index("ix_review_queue_status_priority", "review_queue", ["status", "priority"], unique=False)

    op.create_table(
        "ai_copy_drafts",
        sa.Column("deal_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("copy_type", ai_copy_type_enum, nullable=False),
        sa.Column("status", ai_copy_draft_status_enum, server_default="draft", nullable=False),
        sa.Column("model_name", sa.String(length=120), nullable=True),
        sa.Column("prompt_version", sa.String(length=64), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["deal_id"], ["deals.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_copy_drafts_copy_type", "ai_copy_drafts", ["copy_type"], unique=False)
    op.create_index("ix_ai_copy_drafts_deal_id_status", "ai_copy_drafts", ["deal_id", "status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_ai_copy_drafts_deal_id_status", table_name="ai_copy_drafts")
    op.drop_index("ix_ai_copy_drafts_copy_type", table_name="ai_copy_drafts")
    op.drop_table("ai_copy_drafts")

    op.drop_index("ix_review_queue_status_priority", table_name="review_queue")
    op.drop_index("ix_review_queue_product_source_record_id", table_name="review_queue")
    op.drop_index("ix_review_queue_entity_type_entity_id", table_name="review_queue")
    op.drop_table("review_queue")

    op.drop_index("ix_deals_status_starts_at", table_name="deals")
    op.drop_index("ix_deals_source_id_detected_at", table_name="deals")
    op.drop_index("ix_deals_product_variant_id", table_name="deals")
    op.drop_index("ix_deals_ends_at", table_name="deals")
    op.drop_table("deals")

    op.drop_index("ix_price_statistics_variant_window", table_name="price_statistics")
    op.drop_index("ix_price_statistics_source_observed_on", table_name="price_statistics")
    op.drop_table("price_statistics")

    op.drop_index("ix_price_observations_total_price", table_name="price_observations")
    op.drop_index("ix_price_observations_sale_price", table_name="price_observations")
    op.drop_index("ix_price_observations_record_id_observed_at", table_name="price_observations")
    op.drop_table("price_observations")

    op.drop_index("ix_product_source_records_source_id_last_seen_at", table_name="product_source_records")
    op.drop_index("ix_product_source_records_product_variant_id", table_name="product_source_records")
    op.drop_index("ix_product_source_records_product_id", table_name="product_source_records")
    op.drop_index("ix_product_source_records_merchant_id", table_name="product_source_records")
    op.drop_index("ix_product_source_records_availability_status", table_name="product_source_records")
    op.drop_table("product_source_records")

    op.drop_index("ix_product_variants_sku", table_name="product_variants")
    op.drop_index("ix_product_variants_product_id", table_name="product_variants")
    op.drop_index("ix_product_variants_gtin", table_name="product_variants")
    op.drop_table("product_variants")

    op.drop_index("ix_products_normalized_name", table_name="products")
    op.drop_index("ix_products_merchant_id", table_name="products")
    op.drop_index("ix_products_brand", table_name="products")
    op.drop_table("products")

    op.drop_index("ix_merchants_country_code", table_name="merchants")
    op.drop_index("ix_merchants_canonical_name", table_name="merchants")
    op.drop_table("merchants")

    op.drop_index("ix_sources_source_type_is_active", table_name="sources")
    op.drop_table("sources")

    bind = op.get_bind()
    ai_copy_draft_status_enum.drop(bind, checkfirst=True)
    ai_copy_type_enum.drop(bind, checkfirst=True)
    review_type_enum.drop(bind, checkfirst=True)
    review_status_enum.drop(bind, checkfirst=True)
    deal_status_enum.drop(bind, checkfirst=True)
    price_statistic_window_enum.drop(bind, checkfirst=True)
    availability_status_enum.drop(bind, checkfirst=True)
    source_type_enum.drop(bind, checkfirst=True)
