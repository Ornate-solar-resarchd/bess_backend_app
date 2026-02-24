"""add shipment created and expected arrival dates

Revision ID: d2a9f6c1b7e4
Revises: b7f2e3d9c4a1
Create Date: 2026-02-24 13:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d2a9f6c1b7e4"
down_revision: Union[str, Sequence[str], None] = "b7f2e3d9c4a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("shipments", sa.Column("created_date", sa.Date(), nullable=True))
    op.add_column("shipments", sa.Column("expected_arrival_date", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("shipments", "expected_arrival_date")
    op.drop_column("shipments", "created_date")
