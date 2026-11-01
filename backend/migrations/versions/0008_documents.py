"""documents: folders, documents, versions and reviews

Revision ID: 0008
Revises: 0007
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.documents.folders import EVENT_FOLDERS

revision: str = '0008'
down_revision: str | None = '0007'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('folders',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=True), nullable=False),
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('event_id', sa.BigInteger(), nullable=True),
    sa.Column('sort_order', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('created_by', sa.BigInteger(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['users.id']),
    sa.ForeignKeyConstraint(['event_id'], ['events.id']),
    sa.PrimaryKeyConstraint('id'))
    op.create_index(op.f('ix_folders_event_id'), 'folders', ['event_id'])
    op.create_table('documents',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=True), nullable=False),
    sa.Column('folder_id', sa.BigInteger(), nullable=False),
    sa.Column('title', sa.Text(), nullable=False),
    sa.Column('category', sa.Text(), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('status', sa.Text(), server_default='draft', nullable=False),
    sa.Column('created_by', sa.BigInteger(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('deleted_by', sa.BigInteger(), nullable=True),
    sa.CheckConstraint("status IN ('draft', 'submitted', 'approved', 'rejected', 'final', 'archived')", name='documents_status_check'),
    sa.ForeignKeyConstraint(['created_by'], ['users.id']),
    sa.ForeignKeyConstraint(['deleted_by'], ['users.id']),
    sa.ForeignKeyConstraint(['folder_id'], ['folders.id']),
    sa.PrimaryKeyConstraint('id'))
    op.create_index(op.f('ix_documents_folder_id'), 'documents', ['folder_id'])
    op.create_table('document_versions',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=True), nullable=False),
    sa.Column('document_id', sa.BigInteger(), nullable=False),
    sa.Column('version_no', sa.Integer(), nullable=False),
    sa.Column('storage_key', sa.Text(), nullable=False),
    sa.Column('original_filename', sa.Text(), nullable=False),
    sa.Column('mime_type', sa.Text(), nullable=False),
    sa.Column('size_bytes', sa.BigInteger(), nullable=False),
    sa.Column('sha256', sa.LargeBinary(), nullable=False),
    sa.Column('uploaded_by', sa.BigInteger(), nullable=False),
    sa.Column('uploaded_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('size_bytes > 0', name='document_versions_size_check'),
    sa.ForeignKeyConstraint(['document_id'], ['documents.id']),
    sa.ForeignKeyConstraint(['uploaded_by'], ['users.id']),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('document_id', 'version_no', name='document_versions_no_key'),
    sa.UniqueConstraint('storage_key'))
    op.create_index(op.f('ix_document_versions_document_id'), 'document_versions', ['document_id'])
    op.create_table('document_reviews',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=True), nullable=False),
    sa.Column('document_id', sa.BigInteger(), nullable=False),
    sa.Column('from_status', sa.Text(), nullable=True),
    sa.Column('to_status', sa.Text(), nullable=False),
    sa.Column('remarks', sa.Text(), nullable=True),
    sa.Column('reviewer_id', sa.BigInteger(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['document_id'], ['documents.id']),
    sa.ForeignKeyConstraint(['reviewer_id'], ['users.id']),
    sa.PrimaryKeyConstraint('id'))
    op.create_index(op.f('ix_document_reviews_document_id'), 'document_reviews', ['document_id'])
    op.execute("""CREATE TRIGGER document_versions_append_only BEFORE UPDATE OR DELETE ON document_versions
                  FOR EACH ROW EXECUTE FUNCTION forbid_mutation()""")
    # Events that already exist get the same starting folders as new ones.
    folders = sa.table('folders', sa.column('name'), sa.column('event_id'), sa.column('sort_order'), sa.column('created_by'))
    bind = op.get_bind()
    for event_id, owner_id in bind.execute(sa.text('SELECT id, owner_id FROM events')).all():
        op.bulk_insert(folders, [{"name": name, "event_id": event_id, "sort_order": i, "created_by": owner_id}
                                 for i, name in enumerate(EVENT_FOLDERS, start=1)])


def downgrade() -> None:
    op.execute("DROP TRIGGER document_versions_append_only ON document_versions")
    op.drop_table('document_reviews')
    op.drop_table('document_versions')
    op.drop_table('documents')
    op.drop_table('folders')
