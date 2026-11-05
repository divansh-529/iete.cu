"""paid members no longer carry a father name

Revision ID: 0015
Revises: 0014
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0015'
down_revision: str | None = '0014'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column('memberships', 'father_name')


def downgrade() -> None:
    # The names themselves aren't restored.
    op.add_column('memberships', sa.Column('father_name', sa.Text()))
