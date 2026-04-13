"""add asin ingestion checkpoints

Revision ID: 20260411_0015
Revises: 20260410_0014
Create Date: 2026-04-11 10:30:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260411_0015"
down_revision = "20260410_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "asin_ingestion_checkpoints",
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("asin", sa.String(length=16), nullable=False),
        sa.Column("last_processed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_id", "asin", name="uq_asin_ingestion_checkpoints_source_asin"),
    )
    op.create_index(
        "ix_asin_ingestion_checkpoints_source_id_last_processed_at",
        "asin_ingestion_checkpoints",
        ["source_id", "last_processed_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_asin_ingestion_checkpoints_source_id_last_processed_at",
        table_name="asin_ingestion_checkpoints",
    )
    op.drop_table("asin_ingestion_checkpoints")
