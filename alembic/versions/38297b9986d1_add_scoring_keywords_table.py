"""add scoring_keywords table

Revision ID: 38297b9986d1
Revises: 20260412_0019
Create Date: 2026-04-15 23:17:37.185747
"""
import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = '38297b9986d1'
down_revision = '20260412_0019'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'scoring_keywords',
        sa.Column('id', sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('list_name', sa.String(64), nullable=False),
        sa.Column('keyword', sa.String(255), nullable=False),
        sa.Column('enabled', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('list_name', 'keyword', name='uq_scoring_keywords_list_keyword'),
    )
    op.create_index('ix_scoring_keywords_list_name', 'scoring_keywords', ['list_name'])


def downgrade() -> None:
    op.drop_index('ix_scoring_keywords_list_name', table_name='scoring_keywords')
    op.drop_table('scoring_keywords')
