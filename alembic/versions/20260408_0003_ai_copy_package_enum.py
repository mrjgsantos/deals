"""add ai copy package enum value

Revision ID: 20260408_0003
Revises: 20260408_0002
Create Date: 2026-04-08 23:10:00
"""

from typing import Sequence, Union

from alembic import op


revision: str = "20260408_0003"
down_revision: Union[str, None] = "20260408_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE ai_copy_type_enum ADD VALUE IF NOT EXISTS 'package';")


def downgrade() -> None:
    pass
