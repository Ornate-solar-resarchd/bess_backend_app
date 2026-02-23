"""enforce single shipment per bess unit

Revision ID: 9e5d4c7b1a2f
Revises: c31e7a9f2b44
Create Date: 2026-02-23 16:20:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9e5d4c7b1a2f"
down_revision: Union[str, Sequence[str], None] = "c31e7a9f2b44"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


DUPLICATE_CHECK_SQL = sa.text(
    """
    SELECT bess_unit_id
    FROM shipment_items
    GROUP BY bess_unit_id
    HAVING COUNT(*) > 1
    LIMIT 1
    """
)


def upgrade() -> None:
    bind = op.get_bind()
    duplicate_bess_id = bind.execute(DUPLICATE_CHECK_SQL).scalar_one_or_none()
    if duplicate_bess_id is not None:
        raise RuntimeError(
            "Cannot enforce single-shipment rule. "
            f"bess_unit_id={duplicate_bess_id} is linked to multiple shipments. "
            "Clean duplicate shipment_items rows first."
        )

    op.create_unique_constraint(
        "uq_shipment_items_bess_unit_id",
        "shipment_items",
        ["bess_unit_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_shipment_items_bess_unit_id", "shipment_items", type_="unique")
