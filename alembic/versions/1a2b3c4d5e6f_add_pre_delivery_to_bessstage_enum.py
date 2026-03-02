"""add new bessstage enum values

Revision ID: 1a2b3c4d5e6f
Revises: f14c0a8d9b27
Create Date: 2026-03-02 17:10:00.000000
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "1a2b3c4d5e6f"
down_revision = "f14c0a8d9b27"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE bessstage ADD VALUE IF NOT EXISTS 'PRE_DELIVERY' AFTER 'WAREHOUSE_STORED'")
    op.execute("ALTER TYPE bessstage ADD VALUE IF NOT EXISTS 'PRE_INSTALLATION' AFTER 'SITE_ARRIVED'")
    op.execute("ALTER TYPE bessstage ADD VALUE IF NOT EXISTS 'POST_INSTALLATION' AFTER 'AC_INSTALLATION'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values directly.
    pass
