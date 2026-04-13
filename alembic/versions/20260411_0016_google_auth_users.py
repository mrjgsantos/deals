"""add google auth fields to users

Revision ID: 20260411_0016
Revises: 20260411_0015
Create Date: 2026-04-11 00:16:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260411_0016"
down_revision = "20260411_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("google_sub", sa.String(length=255), nullable=True))
    op.add_column("users", sa.Column("display_name", sa.String(length=255), nullable=True))
    op.add_column("users", sa.Column("avatar_url", sa.String(length=1000), nullable=True))
    op.create_unique_constraint("uq_users_google_sub", "users", ["google_sub"])
    op.create_index("ix_users_google_sub", "users", ["google_sub"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_users_google_sub", table_name="users")
    op.drop_constraint("uq_users_google_sub", "users", type_="unique")
    op.drop_column("users", "avatar_url")
    op.drop_column("users", "display_name")
    op.drop_column("users", "google_sub")
