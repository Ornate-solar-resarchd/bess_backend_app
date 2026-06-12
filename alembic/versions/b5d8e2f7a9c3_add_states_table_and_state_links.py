"""add states table and state links on cities and bess_units

Revision ID: b5d8e2f7a9c3
Revises: f14c0a8d9b27
Create Date: 2026-06-12 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "b5d8e2f7a9c3"
down_revision: Union[str, Sequence[str], None] = "f14c0a8d9b27"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "states",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("country_id", sa.Integer(), sa.ForeignKey("countries.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("name", "country_id", name="uq_state_country"),
    )
    # Nullable on purpose: rows created by the published mobile app have no state.
    op.add_column("cities", sa.Column("state_id", sa.Integer(), sa.ForeignKey("states.id"), nullable=True))
    op.add_column("bess_units", sa.Column("state_id", sa.Integer(), sa.ForeignKey("states.id"), nullable=True))


def downgrade() -> None:
    op.drop_column("bess_units", "state_id")
    op.drop_column("cities", "state_id")
    op.drop_table("states")
