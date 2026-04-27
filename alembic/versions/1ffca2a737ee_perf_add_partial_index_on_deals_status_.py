"""perf: add partial index on deals status and published_at

Revision ID: 1ffca2a737ee
Revises: 7ea6903abbb6
Create Date: 2026-04-27 10:05:09.291567
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '1ffca2a737ee'
down_revision = '7ea6903abbb6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_deals_status_published_at",
        "deals",
        ["status", sa.text("published_at DESC")],
        postgresql_where=sa.text("published_at IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_deals_status_published_at", table_name="deals")
