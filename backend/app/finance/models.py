"""Accounts, a ledger of transactions, reconciliations and memberships.

Amounts are always positive and is_credit gives the direction, so a book balance is the opening
balance plus posted credits minus posted debits. It is computed, never stored. A posted or rejected
transaction can't change (DB trigger), except that a rejected one can go under appeal; mistakes are
corrected with a reversal.
"""
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (BigInteger, Boolean, CheckConstraint, Date, DateTime, ForeignKey, Identity, Index,
                        LargeBinary, Numeric, Text, UniqueConstraint, func, text)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

TXN_TYPES = ("income", "expense", "transfer_in", "transfer_out", "reversal")
TXN_STATUSES = ("submitted", "verified", "posted", "rejected", "appealed")
PAYMENT_MODES = ("cash", "upi", "bank_transfer", "cheque", "card", "other")
ATTACHMENT_KINDS = ("bill", "invoice", "receipt", "proof", "other")
MEMBERSHIP_STATUSES = ("pending", "paid", "waived", "refunded", "cancelled")


class FinAccount(Base):
    __tablename__ = "fin_accounts"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    name: Mapped[str] = mapped_column(Text, unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    opening_balance: Mapped[Decimal] = mapped_column(Numeric(12, 2), server_default=text("0"))
    opening_date: Mapped[date] = mapped_column(Date)
    active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MembershipCategory(Base):
    __tablename__ = "membership_categories"
    __table_args__ = (CheckConstraint("fee >= 0", name="membership_categories_fee_check"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    name: Mapped[str] = mapped_column(Text, unique=True)
    fee: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))


class Membership(Base):
    """Someone on the team (user_id) or outside it (only the holder_* fields)."""
    __tablename__ = "memberships"
    __table_args__ = (
        CheckConstraint(f"status IN {MEMBERSHIP_STATUSES}", name="memberships_status_check"),
        CheckConstraint("fee_amount >= 0", name="memberships_fee_check"),
        CheckConstraint("valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from", name="memberships_dates_check"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    membership_no: Mapped[str] = mapped_column(Text, unique=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    holder_name: Mapped[str] = mapped_column(Text)
    father_name: Mapped[str | None] = mapped_column(Text)
    course: Mapped[str | None] = mapped_column(Text)
    study_year: Mapped[str | None] = mapped_column(Text)
    holder_uid: Mapped[str | None] = mapped_column(Text)
    holder_email: Mapped[str | None] = mapped_column(Text)
    # Empty for paid members loaded from the Treasurer's list, whose fee was collected before the portal.
    category_id: Mapped[int | None] = mapped_column(ForeignKey("membership_categories.id"))
    fee_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    status: Mapped[str] = mapped_column(Text, server_default="pending")
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    recorded_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FinTransaction(Base):
    __tablename__ = "fin_transactions"
    __table_args__ = (
        CheckConstraint(f"txn_type IN {TXN_TYPES}", name="fin_transactions_type_check"),
        CheckConstraint(f"status IN {TXN_STATUSES}", name="fin_transactions_status_check"),
        CheckConstraint(f"payment_mode IN {PAYMENT_MODES}", name="fin_transactions_mode_check"),
        CheckConstraint("amount > 0", name="fin_transactions_amount_check"),
        # Nobody checks their own spending, enforced here as well as in the service.
        CheckConstraint("verified_by IS NULL OR verified_by <> submitted_by", name="fin_transactions_verifier_check"),
        CheckConstraint("approved_by IS NULL OR approved_by <> submitted_by", name="fin_transactions_approver_check"),
        CheckConstraint("(txn_type IN ('transfer_in', 'transfer_out')) = (transfer_group_id IS NOT NULL)",
                        name="fin_transactions_transfer_check"),
        CheckConstraint("(txn_type = 'reversal') = (reverses_id IS NOT NULL)", name="fin_transactions_reversal_check"),
        Index("fin_transactions_account_status_idx", "account_id", "status"),
        Index("fin_transactions_one_reversal", "reverses_id", unique=True, postgresql_where=text("reverses_id IS NOT NULL")),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    code: Mapped[str] = mapped_column(Text, unique=True)                  # 'EXP-2026-0042'
    txn_type: Mapped[str] = mapped_column(Text)
    is_credit: Mapped[bool] = mapped_column(Boolean)
    account_id: Mapped[int] = mapped_column(ForeignKey("fin_accounts.id"))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    txn_date: Mapped[date] = mapped_column(Date)
    counterparty: Mapped[str | None] = mapped_column(Text)                # source (income) or paid to (expense)
    purpose: Mapped[str] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(Text)
    payment_mode: Mapped[str | None] = mapped_column(Text)
    payment_reference: Mapped[str | None] = mapped_column(Text)
    event_id: Mapped[int | None] = mapped_column(ForeignKey("events.id"), index=True)
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"))
    membership_id: Mapped[int | None] = mapped_column(ForeignKey("memberships.id"))
    transfer_group_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    reverses_id: Mapped[int | None] = mapped_column(ForeignKey("fin_transactions.id"))
    status: Mapped[str] = mapped_column(Text, server_default="submitted")
    submitted_by: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    verified_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejection_reason: Mapped[str | None] = mapped_column(Text)


class FinAttachment(Base):
    __tablename__ = "fin_attachments"
    __table_args__ = (CheckConstraint(f"kind IN {ATTACHMENT_KINDS}", name="fin_attachments_kind_check"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    transaction_id: Mapped[int] = mapped_column(ForeignKey("fin_transactions.id"), index=True)
    kind: Mapped[str] = mapped_column(Text)
    storage_key: Mapped[str] = mapped_column(Text, unique=True)
    original_filename: Mapped[str] = mapped_column(Text)
    mime_type: Mapped[str] = mapped_column(Text)
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[bytes] = mapped_column(LargeBinary)
    added_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FinAppeal(Base):
    """One round of appeal against a rejection. The rejection reason is copied here because a further
    rejection replaces it on the transaction."""
    __tablename__ = "fin_appeals"
    __table_args__ = (
        CheckConstraint("outcome IN ('approved', 'rejected')", name="fin_appeals_outcome_check"),
        Index("fin_appeals_one_open", "transaction_id", unique=True, postgresql_where=text("decided_at IS NULL")),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    transaction_id: Mapped[int] = mapped_column(ForeignKey("fin_transactions.id"), index=True)
    note: Mapped[str] = mapped_column(Text)
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    submitted_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    outcome: Mapped[str | None] = mapped_column(Text)
    decision_note: Mapped[str | None] = mapped_column(Text)


class FinAppealComment(Base):
    __tablename__ = "fin_appeal_comments"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    appeal_id: Mapped[int] = mapped_column(ForeignKey("fin_appeals.id"), index=True)
    body: Mapped[str] = mapped_column(Text)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FinReconciliation(Base):
    """Bank statement against the books at a date. A record, so it is never edited."""
    __tablename__ = "fin_reconciliations"
    __table_args__ = (UniqueConstraint("account_id", "period_end", name="fin_reconciliations_one_per_date"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("fin_accounts.id"))
    period_end: Mapped[date] = mapped_column(Date)
    statement_balance: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    book_balance: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    notes: Mapped[str | None] = mapped_column(Text)
    reconciled_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    reconciled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
