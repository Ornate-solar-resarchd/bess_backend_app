"""add sites master and shipment logistics fields

Revision ID: e3f9c7a1b2d4
Revises: d2a9f6c1b7e4
Create Date: 2026-02-26 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "e3f9c7a1b2d4"
down_revision: Union[str, Sequence[str], None] = "d2a9f6c1b7e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for value in (
            "PORT_CLEARED",
            "WAREHOUSE_STORED",
            "DISPATCHED_TO_SITE",
            "SITE_ARRIVED",
        ):
            op.execute(sa.text(f"ALTER TYPE shipmentstatus ADD VALUE IF NOT EXISTS '{value}'"))

    op.create_table(
        "sites",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("country_id", sa.Integer(), nullable=False),
        sa.Column("city_id", sa.Integer(), nullable=False),
        sa.Column("address", sa.Text(), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["country_id"], ["countries.id"]),
        sa.ForeignKeyConstraint(["city_id"], ["cities.id"]),
    )
    op.create_index("ix_sites_country_id", "sites", ["country_id"], unique=False)
    op.create_index("ix_sites_city_id", "sites", ["city_id"], unique=False)

    op.add_column("shipments", sa.Column("warehouse_id", sa.Integer(), nullable=True))
    op.add_column("shipments", sa.Column("site_id", sa.Integer(), nullable=True))
    op.create_index("ix_shipments_warehouse_id", "shipments", ["warehouse_id"], unique=False)
    op.create_index("ix_shipments_site_id", "shipments", ["site_id"], unique=False)
    op.create_foreign_key(
        "fk_shipments_warehouse_id",
        "shipments",
        "warehouses",
        ["warehouse_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_shipments_site_id",
        "shipments",
        "sites",
        ["site_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_shipments_site_id", "shipments", type_="foreignkey")
    op.drop_constraint("fk_shipments_warehouse_id", "shipments", type_="foreignkey")
    op.drop_index("ix_shipments_site_id", table_name="shipments")
    op.drop_index("ix_shipments_warehouse_id", table_name="shipments")
    op.drop_column("shipments", "site_id")
    op.drop_column("shipments", "warehouse_id")

    op.drop_index("ix_sites_city_id", table_name="sites")
    op.drop_index("ix_sites_country_id", table_name="sites")
    op.drop_table("sites")
