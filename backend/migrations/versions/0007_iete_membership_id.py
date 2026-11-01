"""iete membership id on member profiles

Revision ID: 0007
Revises: 0006
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0007'
down_revision: str | None = '0006'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('member_profiles', sa.Column('iete_membership_id', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('member_profiles', 'iete_membership_id')
