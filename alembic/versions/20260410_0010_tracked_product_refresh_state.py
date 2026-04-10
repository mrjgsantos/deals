"""add tracked product refresh state columns

Revision ID: 20260410_0010
Revises: 20260409_0009
Create Date: 2026-04-10 00:10:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260410_0010"
down_revision = "20260409_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tracked_products", sa.Column("last_refresh_attempt_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("tracked_products", sa.Column("last_refresh_succeeded_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("tracked_products", sa.Column("last_refresh_status", sa.String(length=32), nullable=True))
    op.add_column("tracked_products", sa.Column("last_refresh_failure_reason", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("tracked_products", "last_refresh_failure_reason")
    op.drop_column("tracked_products", "last_refresh_status")
    op.drop_column("tracked_products", "last_refresh_succeeded_at")
    op.drop_column("tracked_products", "last_refresh_attempt_at")
