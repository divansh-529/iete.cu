"""official email and current block on member profiles

Revision ID: 0009
Revises: 0008
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0009'
down_revision: str | None = '0008'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('member_profiles', sa.Column('official_email', sa.Text(), nullable=True))
    op.add_column('member_profiles', sa.Column('block', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('member_profiles', 'block')
    op.drop_column('member_profiles', 'official_email')
