"""Finance and membership. An expense is submitted, verified, then approved, and only then counts in
a balance. Nobody verifies or approves what they submitted. Income and transfers are recorded by people
trusted to do so and post at once. Anything posted is corrected with a reversal, never an edit."""
import hashlib
import uuid
from datetime import date
from decimal import Decimal
from pathlib import PurePath

from sqlalchemy import case, func, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit import service as audit
from app.core.errors import AppError, forbidden, not_found
from app.core.time import utcnow
from app.documents import storage
from app.documents.service import PREVIEWABLE, check_file
from app.events.models import Event
from app.events.service import event_scope
from app.finance.models import (FinAccount, FinAttachment, FinReconciliation, FinTransaction, Membership,
                                MembershipCategory)
from app.finance.member_upload import read_members
from app.finance.schemas import (AccountIn, CategoryIn, ExpenseIn, IncomeIn, MembershipIn, PaidMemberIn, PayIn,
                                 ReconciliationIn, TransferIn)
from app.notifications.service import notify
from app.org.models import Department, MemberProfile
from app.org.service import department_names, people_by_id
from app.permissions import engine
from app.permissions.engine import GLOBAL, can, department_scope
from app.users.models import User

CHAIRPERSON_ABOVE = Decimal(5000)      # larger expenses need the Chairperson (docs/07-open-decisions.md)
PREFIX = {"income": "INC", "expense": "EXP", "transfer_in": "TRF", "transfer_out": "TRF", "reversal": "REV"}


def _today() -> date:
    return utcnow().date()


def _new_code(db: Session, txn_type: str, on: date) -> str:
    return f"{PREFIX[txn_type]}-{on.year}-{db.scalar(text("SELECT nextval('fin_code_seq')")):04d}"


def _account(db: Session, account_id: int, usable_on: date | None = None) -> FinAccount:
    account = db.get(FinAccount, account_id)
    if account is None:
        raise not_found("Account")
    if usable_on is not None:
        if not account.active:
            raise AppError(409, "ACCOUNT_CLOSED", f"{account.name} is closed.")
        if usable_on < account.opening_date:
            raise AppError(422, "BEFORE_OPENING", f"{account.name} opens on {account.opening_date}, so this date is too early.")
    return account


def _check_date(on: date) -> None:
    if on > _today():
        raise AppError(422, "FUTURE_DATE", "The date can't be in the future.")


def _links(db: Session, body: IncomeIn) -> None:
    if body.event_id is not None and db.get(Event, body.event_id) is None:
        raise not_found("Event")
    if body.department_id is not None:
        dept = db.get(Department, body.department_id)
        if dept is None or dept.status == "deleted":
            raise not_found("Department")


# ---------------------------------------------------------------- accounts

def _posted_totals(as_of: date | None = None):
    credits = func.coalesce(func.sum(case((FinTransaction.is_credit, FinTransaction.amount))), 0)
    debits = func.coalesce(func.sum(case((~FinTransaction.is_credit, FinTransaction.amount))), 0)
    stmt = select(FinTransaction.account_id, credits, debits).where(FinTransaction.status == "posted")
    if as_of is not None:
        stmt = stmt.where(FinTransaction.txn_date <= as_of)
    return stmt.group_by(FinTransaction.account_id)


def accounts(db: Session) -> list[dict]:
    totals = {a: (c, d) for a, c, d in db.execute(_posted_totals()).all()}
    latest = {}
    for r in db.scalars(select(FinReconciliation).order_by(FinReconciliation.period_end)):
        latest[r.account_id] = r
    out = []
    for a in db.scalars(select(FinAccount).order_by(FinAccount.active.desc(), FinAccount.name)):
        c, d = totals.get(a.id, (Decimal(0), Decimal(0)))
        r = latest.get(a.id)
        out.append({"id": a.id, "name": a.name, "description": a.description, "opening_balance": a.opening_balance,
                    "opening_date": a.opening_date, "active": a.active, "credits": c, "debits": d,
                    "book_balance": a.opening_balance + c - d, "reconciled_to": r.period_end if r else None,
                    "reconciled_difference": r.statement_balance - r.book_balance if r else None})
    return out


def _account_snapshot(a: FinAccount) -> dict:
    return {"name": a.name, "opening_balance": str(a.opening_balance), "opening_date": a.opening_date.isoformat(),
            "active": a.active}


def save_account(db: Session, actor: User, body: AccountIn, account_id: int | None = None) -> None:
    account = _account(db, account_id) if account_id else FinAccount(created_by=actor.id)
    before = _account_snapshot(account) if account_id else None
    if account_id and (body.opening_balance != account.opening_balance or body.opening_date != account.opening_date):
        if db.scalar(select(FinTransaction.id).where(FinTransaction.account_id == account.id).limit(1)):
            raise AppError(409, "ACCOUNT_IN_USE", "This account has transactions, so its opening balance and date can't change.")
    account.name, account.description = body.name.strip(), body.description
    account.opening_balance, account.opening_date, account.active = body.opening_balance, body.opening_date, body.active
    db.add(account)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise AppError(409, "NAME_TAKEN", "An account with this name already exists.")
    audit.record(db, actor.id, "finance.account_update" if account_id else "finance.account_create", "fin_account",
                 account.id, before=before, after=_account_snapshot(account))
    db.commit()


# ---------------------------------------------------------------- recording money

def _record(db: Session, actor: User, txn_type: str, is_credit: bool, account: FinAccount, status: str, **fields) -> FinTransaction:
    tx = FinTransaction(code=_new_code(db, txn_type, fields["txn_date"]), txn_type=txn_type, is_credit=is_credit,
                        account_id=account.id, status=status, submitted_by=actor.id,
                        posted_at=utcnow() if status == "posted" else None, **fields)
    db.add(tx)
    db.flush()
    audit.record(db, actor.id, f"finance.{txn_type}", "fin_transaction", tx.id,
                 after={"code": tx.code, "account": account.name, "amount": str(tx.amount), "status": status,
                        "purpose": tx.purpose})
    return tx


def record_income(db: Session, actor: User, body: IncomeIn) -> FinTransaction:
    engine.ensure(db, actor, "finance.income.record")
    _check_date(body.txn_date)
    _links(db, body)
    tx = _record(db, actor, "income", True, _account(db, body.account_id, body.txn_date), "posted",
                 **body.model_dump(exclude={"account_id"}))
    db.commit()
    return tx


def submit_expense(db: Session, actor: User, body: ExpenseIn) -> FinTransaction:
    scope = (event_scope(db, body.event_id) if body.event_id
             else department_scope(db, body.department_id) if body.department_id else GLOBAL)
    _links(db, body)
    if not can(db, actor, "finance.expense.submit", scope):
        raise forbidden("Choose a department or event you can submit expenses for.")
    _check_date(body.txn_date)
    tx = _record(db, actor, "expense", False, _account(db, body.account_id, body.txn_date), "submitted",
                 **body.model_dump(exclude={"account_id"}))
    notify(db, engine.users_who_can(db, "finance.expense.verify", GLOBAL, {actor.id}), "expense.submitted",
           _payload(tx, actor), actor.id)
    db.commit()
    return tx


def transfer(db: Session, actor: User, body: TransferIn) -> FinTransaction:
    if body.from_account_id == body.to_account_id:
        raise AppError(422, "SAME_ACCOUNT", "Choose two different accounts.")
    _check_date(body.txn_date)
    source = _account(db, body.from_account_id, body.txn_date)
    target = _account(db, body.to_account_id, body.txn_date)
    group = uuid.uuid4()
    fields = {"amount": body.amount, "txn_date": body.txn_date, "purpose": body.purpose, "transfer_group_id": group}
    out = _record(db, actor, "transfer_out", False, source, "posted", counterparty=target.name, **fields)
    _record(db, actor, "transfer_in", True, target, "posted", counterparty=source.name, **fields)
    db.commit()
    return out


def _payload(tx: FinTransaction, actor: User, **extra) -> dict:
    return {"transaction_id": tx.id, "code": tx.code, "amount": str(tx.amount), "purpose": tx.purpose, "by": actor.full_name, **extra}


# ---------------------------------------------------------------- expense workflow

def _get(db: Session, user: User, transaction_id: int) -> FinTransaction:
    tx = db.get(FinTransaction, transaction_id)
    if tx is None or not (tx.submitted_by == user.id or can(db, user, "finance.view")):
        raise not_found("Transaction")
    return tx


def _needs_chair(tx: FinTransaction) -> bool:
    return tx.amount > CHAIRPERSON_ABOVE


def _can_verify(db: Session, user: User, tx: FinTransaction) -> bool:
    return (tx.txn_type == "expense" and tx.status == "submitted" and tx.submitted_by != user.id
            and can(db, user, "finance.expense.verify"))


def _can_approve(db: Session, user: User, tx: FinTransaction) -> bool:
    return (tx.txn_type == "expense" and tx.status == "verified" and tx.submitted_by != user.id
            and can(db, user, "finance.expense.approve") and (user.is_super_admin or not _needs_chair(tx)))


def _can_reject(db: Session, user: User, tx: FinTransaction) -> bool:
    return _can_verify(db, user, tx) or _can_approve(db, user, tx)


def _reversed_by(db: Session, tx: FinTransaction) -> FinTransaction | None:
    return db.scalar(select(FinTransaction).where(FinTransaction.reverses_id == tx.id))


def _can_reverse(db: Session, user: User, tx: FinTransaction) -> bool:
    # The Chairperson may correct their own entry: until a Treasurer exists, nobody else could.
    return (tx.status == "posted" and tx.txn_type != "reversal" and _reversed_by(db, tx) is None
            and can(db, user, "finance.expense.approve") and (tx.submitted_by != user.id or user.is_super_admin))


def verify(db: Session, actor: User, transaction_id: int) -> None:
    tx = _get(db, actor, transaction_id)
    if not _can_verify(db, actor, tx):
        raise forbidden("You can't verify this expense.")
    tx.status, tx.verified_by, tx.verified_at = "verified", actor.id, utcnow()
    audit.record(db, actor.id, "finance.expense_verify", "fin_transaction", tx.id, after={"code": tx.code})
    approvers = engine.users_who_can(db, "finance.expense.approve", GLOBAL, {tx.submitted_by})
    if _needs_chair(tx):
        approvers = list(db.scalars(select(User.id).where(User.id.in_(approvers or [0]), User.is_super_admin)))
    notify(db, approvers, "expense.verified", _payload(tx, actor), actor.id)
    db.commit()


def approve(db: Session, actor: User, transaction_id: int) -> None:
    tx = _get(db, actor, transaction_id)
    if not _can_approve(db, actor, tx):
        if tx.status == "verified" and _needs_chair(tx) and not actor.is_super_admin and tx.submitted_by != actor.id:
            raise forbidden(f"Expenses above ₹{CHAIRPERSON_ABOVE:,} need the Chairperson.")
        raise forbidden("You can't approve this expense.")
    now = utcnow()
    tx.status, tx.approved_by, tx.approved_at, tx.posted_at = "posted", actor.id, now, now
    audit.record(db, actor.id, "finance.expense_approve", "fin_transaction", tx.id,
                 after={"code": tx.code, "amount": str(tx.amount)})
    notify(db, [tx.submitted_by], "expense.approved", _payload(tx, actor), actor.id)
    db.commit()


def reject(db: Session, actor: User, transaction_id: int, reason: str) -> None:
    tx = _get(db, actor, transaction_id)
    if not _can_reject(db, actor, tx):
        raise forbidden("You can't reject this expense.")
    tx.status, tx.rejection_reason = "rejected", reason.strip()
    audit.record(db, actor.id, "finance.expense_reject", "fin_transaction", tx.id, after={"code": tx.code, "reason": reason})
    notify(db, [tx.submitted_by], "expense.rejected", _payload(tx, actor, reason=reason), actor.id)
    db.commit()


def reverse(db: Session, actor: User, transaction_id: int, reason: str) -> None:
    """Records the opposite entry. A transfer's two sides are reversed together, and reversing a
    membership payment marks the membership refunded."""
    tx = _get(db, actor, transaction_id)
    if not _can_reverse(db, actor, tx):
        raise forbidden("You can't reverse this transaction.")
    legs = [tx]
    if tx.transfer_group_id:
        legs = list(db.scalars(select(FinTransaction).where(FinTransaction.transfer_group_id == tx.transfer_group_id)))
    today = _today()
    for leg in legs:
        _record(db, actor, "reversal", not leg.is_credit, db.get(FinAccount, leg.account_id), "posted", amount=leg.amount,
                txn_date=today, counterparty=leg.counterparty, purpose=f"Reversal of {leg.code}: {reason.strip()}",
                reverses_id=leg.id, event_id=leg.event_id, department_id=leg.department_id)
    if tx.membership_id:
        db.get(Membership, tx.membership_id).status = "refunded"
    if tx.submitted_by != actor.id:
        notify(db, [tx.submitted_by], "transaction.reversed", _payload(tx, actor, reason=reason), actor.id)
    db.commit()


# ---------------------------------------------------------------- attachments

def _can_attach(db: Session, user: User, tx: FinTransaction) -> bool:
    return (tx.submitted_by == user.id or can(db, user, "finance.expense.verify")
            or can(db, user, "finance.expense.approve") or can(db, user, "finance.income.record"))


def add_attachment(db: Session, actor: User, transaction_id: int, kind: str, filename: str, content: bytes) -> None:
    tx = _get(db, actor, transaction_id)
    if not _can_attach(db, actor, tx):
        raise forbidden()
    name, extension, mime_type = check_file(filename, content)
    a = FinAttachment(transaction_id=tx.id, kind=kind, storage_key=f"finance/{uuid.uuid4().hex}{extension}",
                      original_filename=name, mime_type=mime_type, size_bytes=len(content),
                      sha256=hashlib.sha256(content).digest(), added_by=actor.id)
    storage.put(a.storage_key, content, mime_type)
    db.add(a)
    db.flush()
    audit.record(db, actor.id, "finance.attachment_add", "fin_transaction", tx.id, after={"file": name, "kind": kind})
    db.commit()


def attachment_url(db: Session, user: User, transaction_id: int, attachment_id: int, inline: bool) -> str:
    tx = _get(db, user, transaction_id)
    a = db.get(FinAttachment, attachment_id)
    if a is None or a.transaction_id != tx.id:
        raise not_found("Attachment")
    return storage.presigned_url(a.storage_key, a.original_filename, a.mime_type, inline and a.mime_type in PREVIEWABLE)


# ---------------------------------------------------------------- reading

def _views(db: Session, rows: list[FinTransaction]) -> list[dict]:
    people = people_by_id(db, {t.submitted_by for t in rows})
    names = dict(db.execute(select(FinAccount.id, FinAccount.name).where(FinAccount.id.in_({t.account_id for t in rows}))).all())
    events = dict(db.execute(select(Event.id, Event.name).where(Event.id.in_({t.event_id for t in rows if t.event_id}))).all())
    depts = department_names(db, [t.department_id for t in rows if t.department_id])
    reversals = dict(db.execute(select(FinTransaction.reverses_id, FinTransaction.code).where(
        FinTransaction.reverses_id.in_({t.id for t in rows}))).all())
    return [{"id": t.id, "code": t.code, "txn_type": t.txn_type, "is_credit": t.is_credit,
             "account": {"id": t.account_id, "name": names[t.account_id]}, "amount": t.amount, "txn_date": t.txn_date,
             "counterparty": t.counterparty, "purpose": t.purpose, "category": t.category, "payment_mode": t.payment_mode,
             "payment_reference": t.payment_reference,
             "event": {"id": t.event_id, "name": events[t.event_id]} if t.event_id else None,
             "department": {"id": t.department_id, "name": depts.get(t.department_id, "")} if t.department_id else None,
             "membership_id": t.membership_id, "status": t.status, "submitted_by": people[t.submitted_by],
             "submitted_at": t.submitted_at, "reversed_by_code": reversals.get(t.id)} for t in rows]


def transactions(db: Session, user: User, view: str, account_id: int | None, event_id: int | None, status: str | None,
                 start: date | None, end: date | None, limit: int) -> list[dict]:
    stmt = select(FinTransaction)
    if view == "mine" or not can(db, user, "finance.view"):
        stmt = stmt.where(FinTransaction.submitted_by == user.id)
    elif view == "to_act":
        stmt = stmt.where(FinTransaction.txn_type == "expense", or_(FinTransaction.status == "submitted", FinTransaction.status == "verified"))
    if account_id:
        stmt = stmt.where(FinTransaction.account_id == account_id)
    if event_id:
        stmt = stmt.where(FinTransaction.event_id == event_id)
    if status:
        stmt = stmt.where(FinTransaction.status == status)
    if start:
        stmt = stmt.where(FinTransaction.txn_date >= start)
    if end:
        stmt = stmt.where(FinTransaction.txn_date <= end)
    rows = list(db.scalars(stmt.order_by(FinTransaction.txn_date.desc(), FinTransaction.id.desc()).limit(limit)))
    if view == "to_act":
        rows = [t for t in rows if _can_verify(db, user, t) or _can_approve(db, user, t)]
    return _views(db, rows)


def detail(db: Session, user: User, transaction_id: int) -> dict:
    tx = _get(db, user, transaction_id)
    ids = {tx.verified_by, tx.approved_by}
    attachments = list(db.scalars(select(FinAttachment).where(FinAttachment.transaction_id == tx.id).order_by(FinAttachment.id)))
    people = people_by_id(db, {i for i in ids | {a.added_by for a in attachments} if i})
    original = db.get(FinTransaction, tx.reverses_id) if tx.reverses_id else None
    return {**_views(db, [tx])[0],
            "verified_by": people.get(tx.verified_by), "verified_at": tx.verified_at,
            "approved_by": people.get(tx.approved_by), "approved_at": tx.approved_at, "posted_at": tx.posted_at,
            "rejection_reason": tx.rejection_reason, "reverses_code": original.code if original else None,
            "attachments": [{"id": a.id, "kind": a.kind, "original_filename": a.original_filename, "size_bytes": a.size_bytes,
                             "added_by": people[a.added_by], "added_at": a.added_at} for a in attachments],
            "can_verify": _can_verify(db, user, tx), "can_approve": _can_approve(db, user, tx),
            "can_reject": _can_reject(db, user, tx), "can_reverse": _can_reverse(db, user, tx),
            "can_attach": _can_attach(db, user, tx), "needs_chairperson": _needs_chair(tx) and tx.status in ("submitted", "verified")}


# ---------------------------------------------------------------- reconciliation

def _reconciliation_view(db: Session, r: FinReconciliation, names: dict, people: dict) -> dict:
    return {"id": r.id, "account": {"id": r.account_id, "name": names[r.account_id]}, "period_end": r.period_end,
            "statement_balance": r.statement_balance, "book_balance": r.book_balance,
            "difference": r.statement_balance - r.book_balance, "notes": r.notes,
            "reconciled_by": people[r.reconciled_by], "reconciled_at": r.reconciled_at}


def reconciliations(db: Session) -> list[dict]:
    rows = list(db.scalars(select(FinReconciliation).order_by(FinReconciliation.period_end.desc(), FinReconciliation.id.desc())))
    names = dict(db.execute(select(FinAccount.id, FinAccount.name)).all())
    people = people_by_id(db, {r.reconciled_by for r in rows})
    return [_reconciliation_view(db, r, names, people) for r in rows]


def reconcile(db: Session, actor: User, body: ReconciliationIn) -> None:
    _check_date(body.period_end)
    account = _account(db, body.account_id)
    if body.period_end < account.opening_date:
        raise AppError(422, "BEFORE_OPENING", f"{account.name} opens on {account.opening_date}, so this date is too early.")
    if db.scalar(select(FinReconciliation.id).where(FinReconciliation.account_id == account.id,
                                                    FinReconciliation.period_end == body.period_end)):
        raise AppError(409, "ALREADY_RECONCILED", "This account is already reconciled for that date.")
    row = db.execute(_posted_totals(body.period_end).where(FinTransaction.account_id == account.id)).first()
    credits, debits = (row[1], row[2]) if row else (Decimal(0), Decimal(0))
    r = FinReconciliation(account_id=account.id, period_end=body.period_end, statement_balance=body.statement_balance,
                          book_balance=account.opening_balance + credits - debits, notes=body.notes, reconciled_by=actor.id)
    db.add(r)
    db.flush()
    audit.record(db, actor.id, "finance.reconcile", "fin_account", account.id,
                 after={"period_end": body.period_end.isoformat(), "statement": str(r.statement_balance), "book": str(r.book_balance)})
    db.commit()


# ---------------------------------------------------------------- membership

def categories(db: Session) -> list[MembershipCategory]:
    return list(db.scalars(select(MembershipCategory).order_by(MembershipCategory.active.desc(), MembershipCategory.name)))


def save_category(db: Session, actor: User, body: CategoryIn, category_id: int | None = None) -> None:
    category = db.get(MembershipCategory, category_id) if category_id else MembershipCategory()
    if category is None:
        raise not_found("Category")
    category.name, category.fee, category.active = body.name.strip(), body.fee, body.active
    db.add(category)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise AppError(409, "NAME_TAKEN", "A category with this name already exists.")
    audit.record(db, actor.id, "membership.category_save", "membership_category", category.id,
                 after={"name": category.name, "fee": str(category.fee), "active": category.active})
    db.commit()


def _membership_view(m: Membership, names: dict) -> dict:
    return {"id": m.id, "membership_no": m.membership_no, "user_id": m.user_id, "holder_name": m.holder_name,
            "father_name": m.father_name, "course": m.course, "study_year": m.study_year,
            "holder_uid": m.holder_uid, "holder_email": m.holder_email,
            "category": {"id": m.category_id, "name": names[m.category_id]} if m.category_id else None,
            "fee_amount": m.fee_amount, "status": m.status, "valid_from": m.valid_from, "valid_to": m.valid_to, "created_at": m.created_at}


def memberships(db: Session, q: str | None, status: str | None, limit: int) -> list[dict]:
    stmt = select(Membership)
    if status:
        stmt = stmt.where(Membership.status == status)
    if q:
        stmt = stmt.where(or_(Membership.holder_name.icontains(q, autoescape=True), Membership.membership_no.icontains(q, autoescape=True),
                              Membership.holder_uid.icontains(q, autoescape=True), Membership.holder_email.icontains(q, autoescape=True),
                              Membership.father_name.icontains(q, autoescape=True)))
    names = dict(db.execute(select(MembershipCategory.id, MembershipCategory.name)).all())
    return [_membership_view(m, names) for m in db.scalars(stmt.order_by(Membership.id.desc()).limit(limit))]


def create_membership(db: Session, actor: User, body: MembershipIn) -> dict:
    category = db.get(MembershipCategory, body.category_id)
    if category is None or not category.active:
        raise AppError(422, "INVALID_CATEGORY", "Choose an active membership category.")
    name, uid, email = (body.holder_name or "").strip(), body.holder_uid, body.holder_email
    if body.user_id is not None:
        user = db.get(User, body.user_id)
        if user is None or user.status == "deleted":
            raise not_found("Person")
        profile = db.get(MemberProfile, user.id)
        name, email, uid = name or user.full_name, email or user.email, uid or (profile.uid if profile else None)
    if len(name) < 2:
        raise AppError(422, "NAME_REQUIRED", "Enter the member's name.")
    if body.valid_from and body.valid_to and body.valid_to < body.valid_from:
        raise AppError(422, "INVALID_DATES", "The end date can't be before the start date.")
    number = db.scalar(text("SELECT nextval('membership_no_seq')"))
    m = Membership(membership_no=f"MEM-{number:04d}", user_id=body.user_id, holder_name=name, holder_uid=uid, holder_email=email,
                   category_id=category.id, fee_amount=category.fee, valid_from=body.valid_from, valid_to=body.valid_to,
                   recorded_by=actor.id)
    db.add(m)
    db.flush()
    audit.record(db, actor.id, "membership.create", "membership", m.id,
                 after={"no": m.membership_no, "category": category.name, "fee": str(category.fee)})
    db.commit()
    return _membership_view(m, {category.id: category.name})


def _paid_member(actor: User, member: dict) -> Membership:
    # The fee was collected outside the portal, so no income is recorded and no fee is added up.
    return Membership(status="paid", fee_amount=Decimal(0), recorded_by=actor.id, **member)


def add_paid_member(db: Session, actor: User, body: PaidMemberIn) -> dict:
    member = {k: v.strip() if isinstance(v, str) else v for k, v in body.model_dump().items()}
    if db.scalar(select(Membership.id).where(Membership.membership_no == member["membership_no"])):
        raise AppError(409, "NUMBER_TAKEN", f"Membership no {member['membership_no']} already exists.")
    m = _paid_member(actor, member)
    db.add(m)
    db.flush()
    audit.record(db, actor.id, "membership.add_paid", "membership", m.id, after={"no": m.membership_no})
    db.commit()
    return _membership_view(m, {})


def upload_paid_members(db: Session, actor: User, filename: str, content: bytes) -> dict:
    """A number already on file updates that person's details, so a renewal list can be uploaded again."""
    members = read_members(filename, content)
    existing = {m.membership_no: m for m in db.scalars(select(Membership).where(
        Membership.membership_no.in_([m["membership_no"] for m in members])))}
    conflicts = [{"field": "Membership no " + no, "message": f"already exists with status {m.status}"}
                 for no, m in existing.items() if m.status != "paid"]
    if conflicts:
        raise AppError(422, "ROWS_INVALID", "Nothing was saved. These numbers belong to memberships that aren't paid.", conflicts[:20])
    created = updated = 0
    for member in members:
        current = existing.get(member["membership_no"])
        if current is None:
            db.add(_paid_member(actor, member))
            created += 1
        elif any(getattr(current, k) != v for k, v in member.items()):
            for k, v in member.items():
                setattr(current, k, v)
            updated += 1
    audit.record(db, actor.id, "membership.upload", "membership", None,
                 after={"file": PurePath(filename.replace("\\", "/")).name, "rows": len(members), "created": created, "updated": updated})
    db.commit()
    return {"created": created, "updated": updated}


def _membership(db: Session, membership_id: int) -> Membership:
    m = db.get(Membership, membership_id)
    if m is None:
        raise not_found("Membership")
    return m


def pay_membership(db: Session, actor: User, membership_id: int, body: PayIn) -> None:
    m = _membership(db, membership_id)
    if m.status != "pending":
        raise AppError(409, "INVALID_STATE", "Only a pending membership can be paid.")
    if m.fee_amount <= 0:
        raise AppError(422, "NO_FEE", "This category has no fee. Mark the membership as waived instead.")
    _check_date(body.paid_on)
    _record(db, actor, "income", True, _account(db, body.account_id, body.paid_on), "posted", amount=m.fee_amount, txn_date=body.paid_on,
            counterparty=m.holder_name, purpose=f"Membership fee {m.membership_no}", category="Membership",
            payment_mode=body.payment_mode, payment_reference=body.payment_reference, membership_id=m.id)
    m.status = "paid"
    audit.record(db, actor.id, "membership.paid", "membership", m.id, after={"no": m.membership_no})
    db.commit()


def set_membership_status(db: Session, actor: User, membership_id: int, status: str, reason: str) -> None:
    m = _membership(db, membership_id)
    allowed = {"waived": ("pending",), "cancelled": ("pending", "waived")}[status]
    if m.status not in allowed:
        if m.status == "paid":
            raise AppError(409, "INVALID_STATE", "This membership is paid. Reverse its payment under Finance to refund it.")
        raise AppError(409, "INVALID_STATE", f"A {m.status} membership can't be marked {status}.")
    before = m.status
    m.status = status
    audit.record(db, actor.id, f"membership.{status}", "membership", m.id, before={"status": before}, after={"status": status, "reason": reason})
    db.commit()


def membership_summary(db: Session) -> dict:
    by_status = dict(db.execute(select(Membership.status, func.count()).group_by(Membership.status)).all())
    rows = db.execute(select(MembershipCategory.name, func.count(Membership.id)).join(Membership, Membership.category_id == MembershipCategory.id)
                      .where(Membership.status.in_(("paid", "waived"))).group_by(MembershipCategory.name).order_by(MembershipCategory.name)).all()
    collected = db.scalar(select(func.coalesce(func.sum(Membership.fee_amount), 0)).where(Membership.status == "paid"))
    return {"by_status": by_status, "by_category": [{"name": n, "count": c} for n, c in rows], "fees_collected": collected}
