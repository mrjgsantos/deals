"""extend user preferences for personalization profile

Revision ID: 20260411_0017
Revises: 20260411_0016
Create Date: 2026-04-11 16:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260411_0017"
down_revision = "20260411_0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("user_preferences", sa.Column("budget_preference", sa.String(length=16), nullable=True))
    op.add_column(
        "user_preferences",
        sa.Column(
            "intent",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "user_preferences",
        sa.Column("has_pets", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column(
        "user_preferences",
        sa.Column("has_kids", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column(
        "user_preferences",
        sa.Column(
            "context_flags",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )

    op.create_table(
        "user_category_signals",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("affinity_score", sa.Numeric(precision=8, scale=4), server_default=sa.text("0"), nullable=False),
        sa.Column("saved_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("clicked_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("negative_affinity", sa.Numeric(precision=8, scale=4), server_default=sa.text("0"), nullable=False),
        sa.Column("last_interacted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "category", name="uq_user_category_signals_user_category"),
    )
    op.create_index(
        "ix_user_category_signals_user_id_affinity_score",
        "user_category_signals",
        ["user_id", "affinity_score"],
        unique=False,
    )
    op.create_index(
        "ix_user_category_signals_user_id_updated_at",
        "user_category_signals",
        ["user_id", "updated_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_user_category_signals_user_id_updated_at", table_name="user_category_signals")
    op.drop_index("ix_user_category_signals_user_id_affinity_score", table_name="user_category_signals")
    op.drop_table("user_category_signals")
    op.drop_column("user_preferences", "context_flags")
    op.drop_column("user_preferences", "has_kids")
    op.drop_column("user_preferences", "has_pets")
    op.drop_column("user_preferences", "intent")
    op.drop_column("user_preferences", "budget_preference")
