"""add tracked products table

Revision ID: 20260409_0009
Revises: 20260409_0008
Create Date: 2026-04-09 23:10:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "20260409_0009"
down_revision: Union[str, None] = "20260409_0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tracked_products",
        sa.Column("asin", sa.String(length=16), nullable=False),
        sa.Column("domain_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("asin", "domain_id", name="uq_tracked_products_asin_domain"),
    )
    op.create_index("ix_tracked_products_last_checked_at", "tracked_products", ["last_checked_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_tracked_products_last_checked_at", table_name="tracked_products")
    op.drop_table("tracked_products")
