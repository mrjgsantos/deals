"""add published_at to deals

Revision ID: 20260409_0007
Revises: 20260409_0006
Create Date: 2026-04-09 15:20:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "20260409_0007"
down_revision: Union[str, None] = "20260409_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("deals", sa.Column("published_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("deals", "published_at")
