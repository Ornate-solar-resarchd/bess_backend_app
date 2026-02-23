"""add stage certificates table

Revision ID: 8c9f6b12d3a1
Revises: a4a2c553be8e
Create Date: 2026-02-21 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "8c9f6b12d3a1"
down_revision: Union[str, Sequence[str], None] = "a4a2c553be8e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bess_stage = postgresql.ENUM(
        "FACTORY_REGISTERED",
        "SHIPMENT_ASSIGNED",
        "PACKED",
        "IN_TRANSIT",
        "PORT_ARRIVED",
        "PORT_CLEARED",
        "WAREHOUSE_STORED",
        "DISPATCHED_TO_SITE",
        "SITE_ARRIVED",
        "CIVIL_INSTALLATION",
        "DC_INSTALLATION",
        "AC_INSTALLATION",
        "PRE_COMMISSION",
        "COLD_COMMISSION",
        "HOT_COMMISSION",
        "FINAL_ACCEPTANCE",
        "ACTIVE",
        name="bessstage",
        create_type=False,
    )

    op.create_table(
        "stage_certificates",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("bess_unit_id", sa.Integer(), nullable=False),
        sa.Column("stage", bess_stage, nullable=False),
        sa.Column("certificate_name", sa.String(length=200), nullable=False),
        sa.Column("certificate_url", sa.String(length=500), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("uploaded_by_user_id", sa.Integer(), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["bess_unit_id"], ["bess_units.id"]),
        sa.ForeignKeyConstraint(["uploaded_by_user_id"], ["users.id"]),
    )
    op.create_index(
        "ix_stage_certificates_bess_unit_id",
        "stage_certificates",
        ["bess_unit_id"],
        unique=False,
    )
    op.create_index(
        "ix_stage_certificates_stage",
        "stage_certificates",
        ["stage"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_stage_certificates_stage", table_name="stage_certificates")
    op.drop_index("ix_stage_certificates_bess_unit_id", table_name="stage_certificates")
    op.drop_table("stage_certificates")
