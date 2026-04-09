"""add raw ingestion records

Revision ID: 20260408_0002
Revises: 20260408_0001
Create Date: 2026-04-08 22:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "20260408_0002"
down_revision: Union[str, None] = "20260408_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "raw_ingestion_records",
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_source_record_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("parser_name", sa.String(length=100), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="pending", nullable=False),
        sa.Column("rejection_reason", sa.String(length=255), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("normalized_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["product_source_record_id"], ["product_source_records.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_raw_ingestion_records_product_source_record_id", "raw_ingestion_records", ["product_source_record_id"], unique=False)
    op.create_index("ix_raw_ingestion_records_source_id_processed_at", "raw_ingestion_records", ["source_id", "processed_at"], unique=False)
    op.create_index("ix_raw_ingestion_records_status", "raw_ingestion_records", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_raw_ingestion_records_status", table_name="raw_ingestion_records")
    op.drop_index("ix_raw_ingestion_records_source_id_processed_at", table_name="raw_ingestion_records")
    op.drop_index("ix_raw_ingestion_records_product_source_record_id", table_name="raw_ingestion_records")
    op.drop_table("raw_ingestion_records")
