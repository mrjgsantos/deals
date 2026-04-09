"""add price observation dedup index

Revision ID: 20260409_0006
Revises: 20260409_0005
Create Date: 2026-04-09 00:40:00
"""

from typing import Sequence, Union

from alembic import op


revision: str = "20260409_0006"
down_revision: Union[str, None] = "20260409_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "uq_price_observations_record_id_observed_hash",
        "price_observations",
        ["product_source_record_id", "observed_hash"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_price_observations_record_id_observed_hash", table_name="price_observations")
