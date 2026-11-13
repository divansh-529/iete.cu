"""document tracker: the Chairperson and Vice Chairperson delete (hidden, kept for the audit log), and
the carrier hands a document over to someone who accepts it first

Revision ID: 0017
Revises: 0016
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0017'
down_revision: str | None = '0016'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_KINDS = ("created", "assigned", "step_added", "completed", "cancelled", "submitted", "returned", "signed", "rejected")
NEW_KINDS = OLD_KINDS + ("handover_requested", "handover_accepted", "handover_declined", "handover_withdrawn")


def _kinds(kinds) -> None:
    op.drop_constraint('tracked_document_updates_kind_check', 'tracked_document_updates')
    op.create_check_constraint('tracked_document_updates_kind_check', 'tracked_document_updates', f"kind IN {kinds}")


def upgrade() -> None:
    op.add_column('tracked_documents', sa.Column('deleted_at', sa.DateTime(timezone=True)))
    op.add_column('tracked_documents', sa.Column('deleted_by', sa.BigInteger(), sa.ForeignKey('users.id')))
    op.add_column('tracked_documents', sa.Column('handover_to', sa.BigInteger(), sa.ForeignKey('users.id')))
    op.add_column('tracked_documents', sa.Column('handover_note', sa.Text()))
    op.add_column('tracked_documents', sa.Column('handover_at', sa.DateTime(timezone=True)))
    op.create_index('ix_tracked_documents_handover_to', 'tracked_documents', ['handover_to'])
    _kinds(NEW_KINDS)


def downgrade() -> None:
    op.execute(f"DELETE FROM tracked_document_updates WHERE kind NOT IN {OLD_KINDS}")
    _kinds(OLD_KINDS)
    op.drop_index('ix_tracked_documents_handover_to', 'tracked_documents')
    for column in ('handover_at', 'handover_note', 'handover_to', 'deleted_by', 'deleted_at'):
        op.drop_column('tracked_documents', column)
