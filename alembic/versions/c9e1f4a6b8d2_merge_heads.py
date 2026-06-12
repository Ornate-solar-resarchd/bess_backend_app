"""merge branched heads (enum branch, logistics branch, states branch)

Revision ID: c9e1f4a6b8d2
Revises: a1b2c3d4e5f6, e3f9c7a1b2d4, b5d8e2f7a9c3
Create Date: 2026-06-12 00:05:00.000000
"""

from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = "c9e1f4a6b8d2"
down_revision: Union[str, Sequence[str], None] = ("a1b2c3d4e5f6", "e3f9c7a1b2d4", "b5d8e2f7a9c3")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
