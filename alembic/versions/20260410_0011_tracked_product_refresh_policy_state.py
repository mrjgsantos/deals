"""add tracked product refresh policy state

Revision ID: 20260410_0011
Revises: 20260410_0010
Create Date: 2026-04-10 00:11:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260410_0011"
down_revision = "20260410_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tracked_products", sa.Column("last_refresh_failed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "tracked_products",
        sa.Column(
            "consecutive_refresh_failures",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column("tracked_products", sa.Column("next_refresh_eligible_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(
        "ix_tracked_products_next_refresh_eligible_at",
        "tracked_products",
        ["next_refresh_eligible_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_tracked_products_next_refresh_eligible_at", table_name="tracked_products")
    op.drop_column("tracked_products", "next_refresh_eligible_at")
    op.drop_column("tracked_products", "consecutive_refresh_failures")
    op.drop_column("tracked_products", "last_refresh_failed_at")
