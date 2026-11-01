"""departments can be deleted by the Chairperson

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-01 13:10:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0005'
down_revision: str | None = '0004'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint('departments_status_check', 'departments', type_='check')
    op.create_check_constraint('departments_status_check', 'departments',
                               "status IN ('active', 'archived', 'deleted')")
    # Names only need to be unique among departments that still exist.
    op.drop_index('departments_name_unique', table_name='departments')
    op.create_index('departments_name_unique', 'departments', [sa.literal_column('lower(name)')], unique=True,
                    postgresql_where=sa.text("status <> 'deleted'"))


def downgrade() -> None:
    op.drop_index('departments_name_unique', table_name='departments')
    op.create_index('departments_name_unique', 'departments', [sa.literal_column('lower(name)')], unique=True)
    op.drop_constraint('departments_status_check', 'departments', type_='check')
    op.create_check_constraint('departments_status_check', 'departments', "status IN ('active', 'archived')")
