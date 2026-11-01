"""finance and membership: accounts, ledger, attachments, reconciliations, memberships

Revision ID: 0013
Revises: 0012
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0013'
down_revision: str | None = '0012'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _id():
    return sa.Column('id', sa.BigInteger(), sa.Identity(always=True), primary_key=True)


def _stamp(name):
    return sa.Column(name, sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False)


def upgrade() -> None:
    op.execute("CREATE SEQUENCE fin_code_seq")
    op.execute("CREATE SEQUENCE membership_no_seq")
    op.create_table('fin_accounts', _id(),
    sa.Column('name', sa.Text(), nullable=False, unique=True),
    sa.Column('description', sa.Text()),
    sa.Column('opening_balance', sa.Numeric(12, 2), server_default=sa.text('0'), nullable=False),
    sa.Column('opening_date', sa.Date(), nullable=False),
    sa.Column('active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('created_by', sa.BigInteger(), sa.ForeignKey('users.id'), nullable=False),
    _stamp('created_at'))
    op.create_table('membership_categories', _id(),
    sa.Column('name', sa.Text(), nullable=False, unique=True),
    sa.Column('fee', sa.Numeric(12, 2), nullable=False),
    sa.Column('active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.CheckConstraint('fee >= 0', name='membership_categories_fee_check'))
    op.create_table('memberships', _id(),
    sa.Column('membership_no', sa.Text(), nullable=False, unique=True),
    sa.Column('user_id', sa.BigInteger(), sa.ForeignKey('users.id')),
    sa.Column('holder_name', sa.Text(), nullable=False),
    sa.Column('father_name', sa.Text()),
    sa.Column('course', sa.Text()),
    sa.Column('study_year', sa.Text()),
    sa.Column('holder_uid', sa.Text()),
    sa.Column('holder_email', sa.Text()),
    sa.Column('category_id', sa.BigInteger(), sa.ForeignKey('membership_categories.id')),
    sa.Column('fee_amount', sa.Numeric(12, 2), nullable=False),
    sa.Column('status', sa.Text(), server_default='pending', nullable=False),
    sa.Column('valid_from', sa.Date()),
    sa.Column('valid_to', sa.Date()),
    sa.Column('recorded_by', sa.BigInteger(), sa.ForeignKey('users.id'), nullable=False),
    _stamp('created_at'),
    sa.CheckConstraint("status IN ('pending', 'paid', 'waived', 'refunded', 'cancelled')", name='memberships_status_check'),
    sa.CheckConstraint('fee_amount >= 0', name='memberships_fee_check'),
    sa.CheckConstraint('valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from', name='memberships_dates_check'))
    op.create_index(op.f('ix_memberships_user_id'), 'memberships', ['user_id'])
    op.create_table('fin_transactions', _id(),
    sa.Column('code', sa.Text(), nullable=False, unique=True),
    sa.Column('txn_type', sa.Text(), nullable=False),
    sa.Column('is_credit', sa.Boolean(), nullable=False),
    sa.Column('account_id', sa.BigInteger(), sa.ForeignKey('fin_accounts.id'), nullable=False),
    sa.Column('amount', sa.Numeric(12, 2), nullable=False),
    sa.Column('txn_date', sa.Date(), nullable=False),
    sa.Column('counterparty', sa.Text()),
    sa.Column('purpose', sa.Text(), nullable=False),
    sa.Column('category', sa.Text()),
    sa.Column('payment_mode', sa.Text()),
    sa.Column('payment_reference', sa.Text()),
    sa.Column('event_id', sa.BigInteger(), sa.ForeignKey('events.id')),
    sa.Column('department_id', sa.BigInteger(), sa.ForeignKey('departments.id')),
    sa.Column('membership_id', sa.BigInteger(), sa.ForeignKey('memberships.id')),
    sa.Column('transfer_group_id', postgresql.UUID(as_uuid=True)),
    sa.Column('reverses_id', sa.BigInteger(), sa.ForeignKey('fin_transactions.id')),
    sa.Column('status', sa.Text(), server_default='submitted', nullable=False),
    sa.Column('submitted_by', sa.BigInteger(), sa.ForeignKey('users.id'), nullable=False),
    _stamp('submitted_at'),
    sa.Column('verified_by', sa.BigInteger(), sa.ForeignKey('users.id')),
    sa.Column('verified_at', sa.DateTime(timezone=True)),
    sa.Column('approved_by', sa.BigInteger(), sa.ForeignKey('users.id')),
    sa.Column('approved_at', sa.DateTime(timezone=True)),
    sa.Column('posted_at', sa.DateTime(timezone=True)),
    sa.Column('rejection_reason', sa.Text()),
    sa.CheckConstraint("txn_type IN ('income', 'expense', 'transfer_in', 'transfer_out', 'reversal')", name='fin_transactions_type_check'),
    sa.CheckConstraint("status IN ('submitted', 'verified', 'posted', 'rejected')", name='fin_transactions_status_check'),
    sa.CheckConstraint("payment_mode IN ('cash', 'upi', 'bank_transfer', 'cheque', 'card', 'other')", name='fin_transactions_mode_check'),
    sa.CheckConstraint('amount > 0', name='fin_transactions_amount_check'),
    sa.CheckConstraint('verified_by IS NULL OR verified_by <> submitted_by', name='fin_transactions_verifier_check'),
    sa.CheckConstraint('approved_by IS NULL OR approved_by <> submitted_by', name='fin_transactions_approver_check'),
    sa.CheckConstraint("(txn_type IN ('transfer_in', 'transfer_out')) = (transfer_group_id IS NOT NULL)", name='fin_transactions_transfer_check'),
    sa.CheckConstraint("(txn_type = 'reversal') = (reverses_id IS NOT NULL)", name='fin_transactions_reversal_check'))
    op.create_index('fin_transactions_account_status_idx', 'fin_transactions', ['account_id', 'status'])
    op.create_index('fin_transactions_one_reversal', 'fin_transactions', ['reverses_id'], unique=True,
                    postgresql_where=sa.text('reverses_id IS NOT NULL'))
    op.create_index(op.f('ix_fin_transactions_event_id'), 'fin_transactions', ['event_id'])
    op.create_index(op.f('ix_fin_transactions_submitted_by'), 'fin_transactions', ['submitted_by'])
    op.create_table('fin_attachments', _id(),
    sa.Column('transaction_id', sa.BigInteger(), sa.ForeignKey('fin_transactions.id'), nullable=False),
    sa.Column('kind', sa.Text(), nullable=False),
    sa.Column('storage_key', sa.Text(), nullable=False, unique=True),
    sa.Column('original_filename', sa.Text(), nullable=False),
    sa.Column('mime_type', sa.Text(), nullable=False),
    sa.Column('size_bytes', sa.BigInteger(), nullable=False),
    sa.Column('sha256', sa.LargeBinary(), nullable=False),
    sa.Column('added_by', sa.BigInteger(), sa.ForeignKey('users.id'), nullable=False),
    _stamp('added_at'),
    sa.CheckConstraint("kind IN ('bill', 'invoice', 'receipt', 'proof', 'other')", name='fin_attachments_kind_check'))
    op.create_index(op.f('ix_fin_attachments_transaction_id'), 'fin_attachments', ['transaction_id'])
    op.create_table('fin_reconciliations', _id(),
    sa.Column('account_id', sa.BigInteger(), sa.ForeignKey('fin_accounts.id'), nullable=False),
    sa.Column('period_end', sa.Date(), nullable=False),
    sa.Column('statement_balance', sa.Numeric(12, 2), nullable=False),
    sa.Column('book_balance', sa.Numeric(12, 2), nullable=False),
    sa.Column('notes', sa.Text()),
    sa.Column('reconciled_by', sa.BigInteger(), sa.ForeignKey('users.id'), nullable=False),
    _stamp('reconciled_at'),
    sa.UniqueConstraint('account_id', 'period_end', name='fin_reconciliations_one_per_date'))
    # Posted and rejected transactions are final, and nothing is ever deleted.
    op.execute("""
CREATE FUNCTION fin_txn_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Finance transactions cannot be deleted; record a reversal';
  END IF;
  IF OLD.status IN ('posted', 'rejected') THEN
    RAISE EXCEPTION 'Transaction % is final; record a reversal', OLD.code;
  END IF;
  RETURN NEW;
END $$""")
    op.execute("""CREATE TRIGGER fin_transactions_guard BEFORE UPDATE OR DELETE ON fin_transactions
                  FOR EACH ROW EXECUTE FUNCTION fin_txn_guard()""")
    op.execute("""CREATE TRIGGER fin_reconciliations_append_only BEFORE UPDATE OR DELETE ON fin_reconciliations
                  FOR EACH ROW EXECUTE FUNCTION forbid_mutation()""")
    # Leads and Leadership spend the forum's money, so they can submit expenses (not sensitive).
    op.execute("""INSERT INTO role_permissions (role_id, permission_code)
                  SELECT r.id, 'finance.expense.submit' FROM roles r
                  WHERE r.name IN ('Leadership', 'Department Lead')
                    AND EXISTS (SELECT 1 FROM permissions p WHERE p.code = 'finance.expense.submit')
                  ON CONFLICT DO NOTHING""")
    op.execute("""INSERT INTO permission_audit (action, permission_code, role_id, reason)
                  SELECT 'role_update', 'finance.expense.submit', r.id, 'Phase 6: leads and leadership submit expenses'
                  FROM roles r WHERE r.name IN ('Leadership', 'Department Lead')""")


def downgrade() -> None:
    op.execute("""DELETE FROM role_permissions WHERE permission_code = 'finance.expense.submit'
                  AND role_id IN (SELECT id FROM roles WHERE name IN ('Leadership', 'Department Lead'))""")
    op.execute("DROP TRIGGER fin_reconciliations_append_only ON fin_reconciliations")
    op.execute("DROP TRIGGER fin_transactions_guard ON fin_transactions")
    op.execute("DROP FUNCTION fin_txn_guard()")
    for table in ('fin_reconciliations', 'fin_attachments', 'fin_transactions', 'memberships', 'membership_categories', 'fin_accounts'):
        op.drop_table(table)
    op.execute("DROP SEQUENCE membership_no_seq")
    op.execute("DROP SEQUENCE fin_code_seq")
