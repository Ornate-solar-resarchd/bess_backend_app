"""add shipment expected quantity and shipment documents

Revision ID: c31e7a9f2b44
Revises: f14c0a8d9b27
Create Date: 2026-02-23 11:20:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c31e7a9f2b44"
down_revision = "f14c0a8d9b27"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "shipments",
        sa.Column("expected_quantity", sa.Integer(), nullable=False, server_default="1"),
    )
    op.alter_column("shipments", "expected_quantity", server_default=None)

    op.create_table(
        "shipment_documents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("shipment_id", sa.Integer(), nullable=False),
        sa.Column("document_name", sa.String(length=255), nullable=False),
        sa.Column("document_type", sa.String(length=100), nullable=True),
        sa.Column("document_url", sa.String(length=500), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("uploaded_by_user_id", sa.Integer(), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["shipment_id"], ["shipments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploaded_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_shipment_documents_document_type", "shipment_documents", ["document_type"], unique=False)
    op.create_index("ix_shipment_documents_shipment_id", "shipment_documents", ["shipment_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_shipment_documents_shipment_id", table_name="shipment_documents")
    op.drop_index("ix_shipment_documents_document_type", table_name="shipment_documents")
    op.drop_table("shipment_documents")
    op.drop_column("shipments", "expected_quantity")
