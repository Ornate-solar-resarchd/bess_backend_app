"""add product_model_id to checklist_templates

Revision ID: d7e3a1f9c2b8
Revises: c9e1f4a6b8d2
Create Date: 2026-06-15

"""
from alembic import op
import sqlalchemy as sa

revision = 'd7e3a1f9c2b8'
down_revision = 'c9e1f4a6b8d2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'checklist_templates',
        sa.Column('product_model_id', sa.Integer(), nullable=True)
    )
    op.create_index(
        'ix_checklist_templates_product_model_id',
        'checklist_templates',
        ['product_model_id']
    )
    op.create_foreign_key(
        'fk_checklist_templates_product_model_id',
        'checklist_templates',
        'product_models',
        ['product_model_id'],
        ['id']
    )


def downgrade() -> None:
    op.drop_constraint('fk_checklist_templates_product_model_id', 'checklist_templates', type_='foreignkey')
    op.drop_index('ix_checklist_templates_product_model_id', table_name='checklist_templates')
    op.drop_column('checklist_templates', 'product_model_id')
