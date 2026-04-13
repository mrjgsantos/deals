"""add last seen deals timestamp to users

Revision ID: 20260412_0018
Revises: 20260411_0017
Create Date: 2026-04-12 10:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260412_0018"
down_revision = "20260411_0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("last_seen_deals_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "last_seen_deals_at")
