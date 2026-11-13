"""document tracker: paper documents carried from office to office for signatures

Revision ID: 0016
Revises: 0015
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0016'
down_revision: str | None = '0015'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TRACKER_STATUSES = ("in_progress", "completed", "rejected", "cancelled")
STEP_STATUSES = ("pending", "submitted", "returned", "signed", "rejected")
TIMELINE_KINDS = ("created", "assigned", "step_added", "completed", "cancelled", "submitted", "returned", "signed", "rejected")


def _id():
    return sa.Column('id', sa.BigInteger(), sa.Identity(always=True), primary_key=True)


def _user(name, nullable=False):
    return sa.Column(name, sa.BigInteger(), sa.ForeignKey('users.id'), nullable=nullable)


def upgrade() -> None:
    op.create_table('tracked_documents', _id(),
    sa.Column('title', sa.Text(), nullable=False),
    sa.Column('reference_no', sa.Text()),
    sa.Column('description', sa.Text()),
    _user('assigned_to'),
    sa.Column('status', sa.Text(), server_default='in_progress', nullable=False),
    _user('created_by'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('closed_at', sa.DateTime(timezone=True)),
    sa.CheckConstraint(f"status IN {TRACKER_STATUSES}", name='tracked_documents_status_check'))
    op.create_index('ix_tracked_documents_assigned_to', 'tracked_documents', ['assigned_to'])
    op.create_index('ix_tracked_documents_created_by', 'tracked_documents', ['created_by'])

    op.create_table('tracked_document_steps', _id(),
    sa.Column('document_id', sa.BigInteger(), sa.ForeignKey('tracked_documents.id'), nullable=False),
    sa.Column('step_no', sa.Integer(), nullable=False),
    sa.Column('authority', sa.Text(), nullable=False),
    sa.Column('status', sa.Text(), server_default='pending', nullable=False),
    sa.CheckConstraint(f"status IN {STEP_STATUSES}", name='tracked_document_steps_status_check'),
    sa.UniqueConstraint('document_id', 'step_no', name='tracked_document_steps_no_key'))
    op.create_index('ix_tracked_document_steps_document_id', 'tracked_document_steps', ['document_id'])

    op.create_table('tracked_document_updates', _id(),
    sa.Column('document_id', sa.BigInteger(), sa.ForeignKey('tracked_documents.id'), nullable=False),
    sa.Column('step_id', sa.BigInteger(), sa.ForeignKey('tracked_document_steps.id')),
    sa.Column('kind', sa.Text(), nullable=False),
    sa.Column('happened_on', sa.Date()),
    sa.Column('note', sa.Text()),
    _user('assigned_to', nullable=True),
    sa.Column('file_key', sa.Text(), unique=True),
    sa.Column('file_name', sa.Text()),
    sa.Column('file_type', sa.Text()),
    _user('by'),
    sa.Column('at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint(f"kind IN {TIMELINE_KINDS}", name='tracked_document_updates_kind_check'))
    op.create_index('ix_tracked_document_updates_document_id', 'tracked_document_updates', ['document_id'])
    # The timeline is a record: lines are added, never changed or removed.
    op.execute("""
CREATE FUNCTION tracker_timeline_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'The document timeline cannot be changed';
END $$""")
    op.execute("""CREATE TRIGGER tracked_document_updates_append_only BEFORE UPDATE OR DELETE ON tracked_document_updates
FOR EACH ROW EXECUTE FUNCTION tracker_timeline_append_only()""")


def downgrade() -> None:
    op.execute("DROP TRIGGER tracked_document_updates_append_only ON tracked_document_updates")
    op.execute("DROP FUNCTION tracker_timeline_append_only()")
    op.drop_table('tracked_document_updates')
    op.drop_table('tracked_document_steps')
    op.drop_table('tracked_documents')
