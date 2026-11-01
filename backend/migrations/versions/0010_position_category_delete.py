"""reporting lines: category boxes, and positions the Chairperson can delete

Revision ID: 0010
Revises: 0009
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0010'
down_revision: str | None = '0009'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('positions', sa.Column('is_category', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    op.drop_constraint('positions_status_check', 'positions', type_='check')
    op.create_check_constraint('positions_status_check', 'positions', "status IN ('active', 'archived', 'deleted')")


def downgrade() -> None:
    op.drop_constraint('positions_status_check', 'positions', type_='check')
    op.create_check_constraint('positions_status_check', 'positions', "status IN ('active', 'archived')")
    op.drop_column('positions', 'is_category')
