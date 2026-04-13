"""add saved deals table

Revision ID: 20260410_0013
Revises: 20260410_0012
Create Date: 2026-04-10 15:30:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260410_0013"
down_revision = "20260410_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "saved_deals",
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "deal_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["deal_id"], ["deals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "deal_id", name="uq_saved_deals_user_deal"),
    )
    op.create_index("ix_saved_deals_deal_id", "saved_deals", ["deal_id"], unique=False)
    op.create_index("ix_saved_deals_user_id_created_at", "saved_deals", ["user_id", "created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_saved_deals_user_id_created_at", table_name="saved_deals")
    op.drop_index("ix_saved_deals_deal_id", table_name="saved_deals")
    op.drop_table("saved_deals")
