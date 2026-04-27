"""perf: add index on ai_copy_drafts deal_id generated_at

Revision ID: 8a0af14a6dc0
Revises: 1ffca2a737ee
Create Date: 2026-04-27 10:11:07.923571
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '8a0af14a6dc0'
down_revision = '1ffca2a737ee'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_ai_copy_drafts_deal_id_generated_at",
        "ai_copy_drafts",
        ["deal_id", sa.text("generated_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_ai_copy_drafts_deal_id_generated_at", table_name="ai_copy_drafts")
