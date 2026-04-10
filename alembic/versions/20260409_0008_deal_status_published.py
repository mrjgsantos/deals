"""add published status to deals

Revision ID: 20260409_0008
Revises: 20260409_0007
Create Date: 2026-04-09 22:35:00
"""

from typing import Sequence, Union

from alembic import op


revision: str = "20260409_0008"
down_revision: Union[str, None] = "20260409_0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE deal_status_enum ADD VALUE IF NOT EXISTS 'published'")


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM pg_type
                WHERE typname = 'deal_status_enum'
            ) THEN
                ALTER TYPE deal_status_enum RENAME TO deal_status_enum_old;
                CREATE TYPE deal_status_enum AS ENUM ('pending_review', 'approved', 'expired', 'rejected');
                ALTER TABLE deals
                    ALTER COLUMN status TYPE deal_status_enum
                    USING CASE
                        WHEN status::text = 'published' THEN 'approved'::deal_status_enum
                        ELSE status::text::deal_status_enum
                    END;
                DROP TYPE deal_status_enum_old;
            END IF;
        END $$;
        """
    )
