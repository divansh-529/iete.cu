"""accounts can be deleted by the Chairperson, and their email can be used again

Revision ID: 0012
Revises: 0011
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0012'
down_revision: str | None = '0011'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD = "('proposed', 'rejected', 'invited', 'active', 'suspended', 'deactivated')"
NEW = "('proposed', 'rejected', 'invited', 'active', 'suspended', 'deactivated', 'deleted')"


def upgrade() -> None:
    op.drop_constraint('users_status_check', 'users', type_='check')
    op.create_check_constraint('users_status_check', 'users', f"status IN {NEW}")
    op.drop_constraint('users_email_key', 'users', type_='unique')
    op.create_index('users_email_unique', 'users', ['email'], unique=True, postgresql_where=sa.text("status <> 'deleted'"))


def downgrade() -> None:
    op.drop_index('users_email_unique', table_name='users', postgresql_where=sa.text("status <> 'deleted'"))
    op.create_unique_constraint('users_email_key', 'users', ['email'])
    op.drop_constraint('users_status_check', 'users', type_='check')
    op.create_check_constraint('users_status_check', 'users', f"status IN {OLD}")
