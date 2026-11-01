"""scoring rounds can be deleted by the Chairperson

Revision ID: 0011
Revises: 0010
"""
from collections.abc import Sequence

from alembic import op

revision: str = '0011'
down_revision: str | None = '0010'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint('score_rounds_status_check', 'score_rounds', type_='check')
    op.create_check_constraint('score_rounds_status_check', 'score_rounds', "status IN ('open', 'closed', 'deleted')")


def downgrade() -> None:
    op.execute("UPDATE score_rounds SET status = 'closed' WHERE status = 'deleted'")
    op.drop_constraint('score_rounds_status_check', 'score_rounds', type_='check')
    op.create_check_constraint('score_rounds_status_check', 'score_rounds', "status IN ('open', 'closed')")
