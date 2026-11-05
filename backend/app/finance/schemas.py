from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, EmailStr, Field

from app.org.schemas import PersonRef

Money = Annotated[Decimal, Field(gt=0, le=Decimal("9999999.99"), decimal_places=2)]
Balance = Annotated[Decimal, Field(ge=Decimal("-9999999.99"), le=Decimal("9999999.99"), decimal_places=2)]
PaymentMode = Literal["cash", "upi", "bank_transfer", "cheque", "card", "other"]
AttachmentKind = Literal["bill", "invoice", "receipt", "proof", "other"]


class Ref(BaseModel):
    id: int
    name: str


class AccountIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    description: str | None = Field(default=None, max_length=500)
    opening_balance: Balance = Decimal(0)
    opening_date: date
    active: bool = True


class AccountOut(BaseModel):
    id: int
    name: str
    description: str | None
    opening_balance: Decimal
    opening_date: date
    active: bool
    credits: Decimal
    debits: Decimal
    book_balance: Decimal
    reconciled_to: date | None
    reconciled_difference: Decimal | None


class IncomeIn(BaseModel):
    account_id: int
    amount: Money
    txn_date: date
    counterparty: str = Field(min_length=2, max_length=120)
    purpose: str = Field(min_length=3, max_length=500)
    category: str | None = Field(default=None, max_length=80)
    payment_mode: PaymentMode
    payment_reference: str | None = Field(default=None, max_length=120)
    event_id: int | None = None
    department_id: int | None = None


class ExpenseIn(IncomeIn):
    pass


class TransferIn(BaseModel):
    from_account_id: int
    to_account_id: int
    amount: Money
    txn_date: date
    purpose: str = Field(min_length=3, max_length=500)


class ReasonIn(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class CommentIn(BaseModel):
    body: str = Field(min_length=1, max_length=1000)


class TransactionOut(BaseModel):
    id: int
    code: str
    txn_type: str
    is_credit: bool
    account: Ref
    amount: Decimal
    txn_date: date
    counterparty: str | None
    purpose: str
    category: str | None
    payment_mode: str | None
    payment_reference: str | None
    event: Ref | None
    department: Ref | None
    membership_id: int | None
    status: str
    submitted_by: PersonRef
    submitted_at: datetime
    reversed_by_code: str | None
    for_chairperson: bool


class AttachmentOut(BaseModel):
    id: int
    kind: str
    original_filename: str
    size_bytes: int
    added_by: PersonRef
    added_at: datetime


class AppealCommentOut(BaseModel):
    id: int
    body: str
    author: PersonRef
    created_at: datetime


class AppealOut(BaseModel):
    id: int
    note: str
    rejection_reason: str | None
    submitted_by: PersonRef
    submitted_at: datetime
    decided_by: PersonRef | None
    decided_at: datetime | None
    outcome: str | None
    decision_note: str | None
    comments: list[AppealCommentOut]


class TransactionDetailOut(TransactionOut):
    verified_by: PersonRef | None
    verified_at: datetime | None
    approved_by: PersonRef | None
    approved_at: datetime | None
    posted_at: datetime | None
    rejection_reason: str | None
    reverses_code: str | None
    attachments: list[AttachmentOut]
    can_verify: bool
    can_approve: bool
    can_reject: bool
    can_reverse: bool
    can_attach: bool
    needs_chairperson: bool
    appeals: list[AppealOut]
    can_appeal: bool
    can_comment: bool


class DownloadOut(BaseModel):
    url: str


class ReconciliationIn(BaseModel):
    account_id: int
    period_end: date
    statement_balance: Balance
    notes: str | None = Field(default=None, max_length=1000)


class ReconciliationOut(BaseModel):
    id: int
    account: Ref
    period_end: date
    statement_balance: Decimal
    book_balance: Decimal
    difference: Decimal
    notes: str | None
    reconciled_by: PersonRef
    reconciled_at: datetime


class CategoryIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    fee: Annotated[Decimal, Field(ge=0, le=Decimal("9999999.99"), decimal_places=2)]
    active: bool = True


class CategoryOut(BaseModel):
    id: int
    name: str
    fee: Decimal
    active: bool


class MembershipIn(BaseModel):
    user_id: int | None = None
    holder_name: str | None = Field(default=None, max_length=120)
    holder_uid: str | None = Field(default=None, max_length=40)
    holder_email: EmailStr | None = None
    category_id: int
    valid_from: date | None = None
    valid_to: date | None = None


class PaidMemberIn(BaseModel):
    holder_name: str = Field(min_length=2, max_length=120)
    membership_no: str = Field(min_length=1, max_length=40)
    course: str = Field(min_length=1, max_length=80)
    study_year: str = Field(min_length=1, max_length=20)
    valid_to: date


class UploadOut(BaseModel):
    created: int
    updated: int


class PayIn(BaseModel):
    account_id: int
    paid_on: date
    payment_mode: PaymentMode
    payment_reference: str | None = Field(default=None, max_length=120)


class MembershipOut(BaseModel):
    id: int
    membership_no: str
    user_id: int | None
    holder_name: str
    course: str | None
    study_year: str | None
    holder_uid: str | None
    holder_email: str | None
    category: Ref | None
    fee_amount: Decimal
    status: str
    valid_from: date | None
    valid_to: date | None
    created_at: datetime


class MembershipSummaryOut(BaseModel):
    by_status: dict[str, int]
    by_category: list[dict[str, str | int]]
    fees_collected: Decimal
