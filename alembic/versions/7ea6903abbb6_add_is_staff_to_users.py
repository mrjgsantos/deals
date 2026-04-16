"""add_is_staff_to_users

Revision ID: 7ea6903abbb6
Revises: 3a2a5bda26bf
Create Date: 2026-04-16 10:59:36.847564
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '7ea6903abbb6'
down_revision = '3a2a5bda26bf'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('is_staff', sa.Boolean(), server_default=sa.text('false'), nullable=False))


def downgrade() -> None:
    op.drop_column('users', 'is_staff')
