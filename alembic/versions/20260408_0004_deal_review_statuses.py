"""add deal review statuses

Revision ID: 20260408_0004
Revises: 20260408_0003
Create Date: 2026-04-08 23:40:00
"""

from typing import Sequence, Union

from alembic import op


revision: str = "20260408_0004"
down_revision: Union[str, None] = "20260408_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE deal_status_enum ADD VALUE IF NOT EXISTS 'pending_review';")
    op.execute("ALTER TYPE deal_status_enum ADD VALUE IF NOT EXISTS 'approved';")


def downgrade() -> None:
    pass
