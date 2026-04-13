"""add user events for lightweight product analytics

Revision ID: 20260412_0019
Revises: 20260412_0018
Create Date: 2026-04-12 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260412_0019"
down_revision = "20260412_0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_events",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("deal_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.ForeignKeyConstraint(["deal_id"], ["deals.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_events_user_id_created_at", "user_events", ["user_id", "created_at"], unique=False)
    op.create_index("ix_user_events_event_type_created_at", "user_events", ["event_type", "created_at"], unique=False)
    op.create_index("ix_user_events_deal_id_event_type", "user_events", ["deal_id", "event_type"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_user_events_deal_id_event_type", table_name="user_events")
    op.drop_index("ix_user_events_event_type_created_at", table_name="user_events")
    op.drop_index("ix_user_events_user_id_created_at", table_name="user_events")
    op.drop_table("user_events")
