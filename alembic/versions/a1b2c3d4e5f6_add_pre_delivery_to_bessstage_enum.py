"""add PRE_DELIVERY to bessstage enum after DISPATCHED_TO_SITE

Revision ID: a1b2c3d4e5f6
Revises: 1a2b3c4d5e6f
Create Date: 2026-03-06 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "1a2b3c4d5e6f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(sa.text("ALTER TYPE bessstage ADD VALUE IF NOT EXISTS 'PRE_DELIVERY'"))


def downgrade() -> None:
    # PostgreSQL does not support removing enum values
    pass
