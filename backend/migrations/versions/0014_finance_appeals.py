"""finance appeals, and team accounts going by position instead of users.view

Revision ID: 0014
Revises: 0013
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0014'
down_revision: str | None = '0013'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _guard(rejected_rule: str) -> str:
    return f"""
CREATE OR REPLACE FUNCTION fin_txn_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Finance transactions cannot be deleted; record a reversal';
  END IF;
  {rejected_rule}
  IF OLD.status IN ('posted', 'rejected') THEN
    RAISE EXCEPTION 'Transaction % is final; record a reversal', OLD.code;
  END IF;
  RETURN NEW;
END $$"""


def upgrade() -> None:
    op.drop_constraint('fin_transactions_status_check', 'fin_transactions')
    op.create_check_constraint('fin_transactions_status_check', 'fin_transactions',
                               "status IN ('submitted', 'verified', 'posted', 'rejected', 'appealed')")
    # A rejected entry can only go under appeal, with nothing else on it changed.
    op.execute(_guard("""IF OLD.status = 'rejected' AND NEW.status = 'appealed'
     AND to_jsonb(NEW) - 'status' = to_jsonb(OLD) - 'status' THEN
    RETURN NEW;
  END IF;"""))
    op.create_table('fin_appeals',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=True), primary_key=True),
    sa.Column('transaction_id', sa.BigInteger(), sa.ForeignKey('fin_transactions.id'), nullable=False),
    sa.Column('note', sa.Text(), nullable=False),
    sa.Column('rejection_reason', sa.Text()),
    sa.Column('submitted_by', sa.BigInteger(), sa.ForeignKey('users.id'), nullable=False),
    sa.Column('submitted_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('decided_by', sa.BigInteger(), sa.ForeignKey('users.id')),
    sa.Column('decided_at', sa.DateTime(timezone=True)),
    sa.Column('outcome', sa.Text()),
    sa.Column('decision_note', sa.Text()),
    sa.CheckConstraint("outcome IN ('approved', 'rejected')", name='fin_appeals_outcome_check'))
    op.create_index(op.f('ix_fin_appeals_transaction_id'), 'fin_appeals', ['transaction_id'])
    op.create_index('fin_appeals_one_open', 'fin_appeals', ['transaction_id'], unique=True,
                    postgresql_where=sa.text('decided_at IS NULL'))
    op.create_table('fin_appeal_comments',
    sa.Column('id', sa.BigInteger(), sa.Identity(always=True), primary_key=True),
    sa.Column('appeal_id', sa.BigInteger(), sa.ForeignKey('fin_appeals.id'), nullable=False),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('author_id', sa.BigInteger(), sa.ForeignKey('users.id'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
    op.create_index(op.f('ix_fin_appeal_comments_appeal_id'), 'fin_appeal_comments', ['appeal_id'])
    op.execute("""CREATE TRIGGER fin_appeal_comments_append_only BEFORE UPDATE OR DELETE ON fin_appeal_comments
                  FOR EACH ROW EXECUTE FUNCTION forbid_mutation()""")
    # Team accounts now go by position, so users.view no longer gives anything.
    op.execute("""INSERT INTO permission_audit (action, permission_code, role_id, reason)
                  SELECT 'role_update', 'users.view', role_id, 'Team accounts now go by position'
                  FROM role_permissions WHERE permission_code = 'users.view'""")
    op.execute("DELETE FROM role_permissions WHERE permission_code = 'users.view'")
    op.execute("""INSERT INTO permission_audit (action, subject_type, subject_id, permission_code, reason)
                  SELECT 'revoke', subject_type, subject_id, 'users.view', 'Team accounts now go by position'
                  FROM grants WHERE permission_code = 'users.view' AND revoked_at IS NULL""")
    op.execute("UPDATE grants SET revoked_at = now() WHERE permission_code = 'users.view' AND revoked_at IS NULL")


def downgrade() -> None:
    # users.view grants stay revoked: bringing them back would widen access without anyone deciding to.
    op.execute("DROP TRIGGER fin_appeal_comments_append_only ON fin_appeal_comments")
    op.drop_table('fin_appeal_comments')
    op.drop_table('fin_appeals')
    op.execute(_guard(""))
    op.drop_constraint('fin_transactions_status_check', 'fin_transactions')
    op.create_check_constraint('fin_transactions_status_check', 'fin_transactions',
                               "status IN ('submitted', 'verified', 'posted', 'rejected')")
