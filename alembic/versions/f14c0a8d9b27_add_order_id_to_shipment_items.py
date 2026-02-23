"""add order id to shipment items

Revision ID: f14c0a8d9b27
Revises: 8c9f6b12d3a1
Create Date: 2026-02-21 00:10:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "f14c0a8d9b27"
down_revision: Union[str, Sequence[str], None] = "8c9f6b12d3a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("shipment_items", sa.Column("order_id", sa.String(length=100), nullable=True))
    op.create_index("ix_shipment_items_order_id", "shipment_items", ["order_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_shipment_items_order_id", table_name="shipment_items")
    op.drop_column("shipment_items", "order_id")
