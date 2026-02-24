"""add nameplate photo url to bess units

Revision ID: b7f2e3d9c4a1
Revises: 9e5d4c7b1a2f
Create Date: 2026-02-24 12:10:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b7f2e3d9c4a1"
down_revision: Union[str, Sequence[str], None] = "9e5d4c7b1a2f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "bess_units",
        sa.Column("nameplate_photo_url", sa.String(length=500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("bess_units", "nameplate_photo_url")
