from collections.abc import Callable
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile
from sqlalchemy.orm import Session

from app.auth.deps import current_user, require, require_in_service
from app.core.db import get_db
from app.core.errors import forbidden
from app.documents.router import _read
from app.finance import service
from app.finance.access import can_record_members, can_view_members, finance_can
from app.finance.schemas import (AccountIn, AccountOut, AttachmentKind, CategoryIn, CategoryOut, CommentIn, DownloadOut, ExpenseIn,
                                 IncomeIn, MembershipIn, MembershipOut, MembershipSummaryOut, PaidMemberIn, PayIn, ReasonIn,
                                 ReconciliationIn, ReconciliationOut, TransactionDetailOut, TransactionOut, TransferIn,
                                 UploadOut)
from app.permissions.engine import has_any
from app.users.models import User

router = APIRouter(prefix="/api", tags=["finance"])

# People who submit an expense always see their own, so transaction routes only require a signed-in
# user and the service checks finance.* or that involvement.


def _finance(permission: str) -> Callable:
    """`require`, also allowing the Treasurer and Joint Secretary by position."""

    def dependency(user: User = Depends(current_user), db: Session = Depends(get_db)) -> User:
        if not finance_can(db, user, permission):
            raise forbidden()
        return user

    dependency.required_permission = permission  # type: ignore[attr-defined]
    return dependency


def _can_submit(user: User = Depends(current_user), db: Session = Depends(get_db)) -> User:
    """Holds it at some scope; the service checks the department or event."""
    if not (has_any(db, user, "finance.expense.submit") or finance_can(db, user, "finance.expense.submit")):
        raise forbidden()
    return user


_can_submit.required_permission = "finance.expense.submit"  # type: ignore[attr-defined]


def _viewer(user: User = Depends(require_in_service("membership.view")), db: Session = Depends(get_db)) -> User:
    if not can_view_members(db, user):
        raise forbidden()
    return user


def _keeper(user: User = Depends(require_in_service("membership.record")), db: Session = Depends(get_db)) -> User:
    if not can_record_members(db, user):
        raise forbidden()
    return user


@router.get("/finance/accounts", response_model=list[AccountOut])
def accounts(_: User = Depends(_finance("finance.view")), db: Session = Depends(get_db)):
    return service.accounts(db)


@router.get("/finance/account-names", response_model=list[dict[str, int | str]])
def account_names(_: User = Depends(_can_submit), db: Session = Depends(get_db)):
    """Just enough for the expense form, without showing balances to people who can't view them."""
    return [{"id": a["id"], "name": a["name"]} for a in service.accounts(db) if a["active"]]


@router.post("/finance/accounts", status_code=204)
def create_account(body: AccountIn, actor: User = Depends(_finance("finance.accounts.manage")), db: Session = Depends(get_db)):
    service.save_account(db, actor, body)
    return Response(status_code=204)


@router.put("/finance/accounts/{account_id}", status_code=204)
def update_account(account_id: int, body: AccountIn, actor: User = Depends(_finance("finance.accounts.manage")),
                   db: Session = Depends(get_db)):
    service.save_account(db, actor, body, account_id)
    return Response(status_code=204)


@router.get("/finance/transactions", response_model=list[TransactionOut])
def transactions(view: Literal["all", "mine", "to_act", "appeals"] = "all", account_id: int | None = None, event_id: int | None = None,
                 status: str | None = None, start: date | None = None, end: date | None = None,
                 limit: int = Query(default=100, ge=1, le=200), user: User = Depends(require_in_service("finance.view")),
                 db: Session = Depends(get_db)):
    return service.transactions(db, user, view, account_id, event_id, status, start, end, limit)


@router.get("/finance/transactions/{transaction_id}", response_model=TransactionDetailOut)
def transaction(transaction_id: int, user: User = Depends(require_in_service("finance.view")), db: Session = Depends(get_db)):
    return service.detail(db, user, transaction_id)


@router.post("/finance/income", response_model=TransactionDetailOut, status_code=201)
def income(body: IncomeIn, actor: User = Depends(_finance("finance.income.record")), db: Session = Depends(get_db)):
    return service.detail(db, actor, service.record_income(db, actor, body).id)


@router.post("/finance/expenses", response_model=TransactionDetailOut, status_code=201)
def expense(body: ExpenseIn, actor: User = Depends(_can_submit), db: Session = Depends(get_db)):
    """The Chairperson's own expense posts at once; anyone else's waits to be verified and approved, or for
    the Chairperson if it is the Treasurer's or Joint Secretary's."""
    return service.detail(db, actor, service.submit_expense(db, actor, body).id)


@router.post("/finance/transfers", response_model=TransactionDetailOut, status_code=201)
def transfer(body: TransferIn, actor: User = Depends(_finance("finance.accounts.manage")), db: Session = Depends(get_db)):
    return service.detail(db, actor, service.transfer(db, actor, body).id)


@router.post("/finance/expenses/{transaction_id}/verify", response_model=TransactionDetailOut)
def verify(transaction_id: int, actor: User = Depends(_finance("finance.expense.verify")), db: Session = Depends(get_db)):
    service.verify(db, actor, transaction_id)
    return service.detail(db, actor, transaction_id)


@router.post("/finance/expenses/{transaction_id}/approve", response_model=TransactionDetailOut)
def approve(transaction_id: int, actor: User = Depends(require("finance.expense.approve")), db: Session = Depends(get_db)):
    service.approve(db, actor, transaction_id)
    return service.detail(db, actor, transaction_id)


@router.post("/finance/expenses/{transaction_id}/reject", response_model=TransactionDetailOut)
def reject(transaction_id: int, body: ReasonIn, actor: User = Depends(require_in_service("finance.expense.verify")),
           db: Session = Depends(get_db)):
    service.reject(db, actor, transaction_id, body.reason)
    return service.detail(db, actor, transaction_id)


@router.post("/finance/transactions/{transaction_id}/appeal", response_model=TransactionDetailOut, status_code=201)
def appeal(transaction_id: int, note: str = Form(), files: list[UploadFile] = File(),
           user: User = Depends(require_in_service("finance.view")), db: Session = Depends(get_db)):
    service.submit_appeal(db, user, transaction_id, note, [(f.filename or "", _read(f)) for f in files])
    return service.detail(db, user, transaction_id)


@router.post("/finance/transactions/{transaction_id}/appeal/comments", response_model=TransactionDetailOut, status_code=201)
def appeal_comment(transaction_id: int, body: CommentIn, user: User = Depends(require_in_service("finance.view")),
                   db: Session = Depends(get_db)):
    service.comment_appeal(db, user, transaction_id, body.body)
    return service.detail(db, user, transaction_id)


@router.post("/finance/transactions/{transaction_id}/reverse", response_model=TransactionDetailOut)
def reverse(transaction_id: int, body: ReasonIn, actor: User = Depends(require("finance.expense.approve")),
            db: Session = Depends(get_db)):
    service.reverse(db, actor, transaction_id, body.reason)
    return service.detail(db, actor, transaction_id)


@router.post("/finance/transactions/{transaction_id}/attachments", response_model=TransactionDetailOut, status_code=201)
def add_attachment(transaction_id: int, kind: AttachmentKind = Form(default="bill"), file: UploadFile = File(),
                   user: User = Depends(require_in_service("finance.view")), db: Session = Depends(get_db)):
    service.add_attachment(db, user, transaction_id, kind, file.filename or "", _read(file))
    return service.detail(db, user, transaction_id)


@router.get("/finance/transactions/{transaction_id}/attachments/{attachment_id}/download", response_model=DownloadOut)
def attachment(transaction_id: int, attachment_id: int, inline: bool = False,
               user: User = Depends(require_in_service("finance.view")), db: Session = Depends(get_db)):
    return {"url": service.attachment_url(db, user, transaction_id, attachment_id, inline)}


@router.get("/finance/reconciliations", response_model=list[ReconciliationOut])
def reconciliations(_: User = Depends(_finance("finance.view")), db: Session = Depends(get_db)):
    return service.reconciliations(db)


@router.post("/finance/reconciliations", status_code=204)
def reconcile(body: ReconciliationIn, actor: User = Depends(_finance("finance.reconcile")), db: Session = Depends(get_db)):
    service.reconcile(db, actor, body)
    return Response(status_code=204)


@router.get("/membership/account-names", response_model=list[dict[str, int | str]])
def membership_account_names(_: User = Depends(_keeper), db: Session = Depends(get_db)):
    return [{"id": a["id"], "name": a["name"]} for a in service.accounts(db) if a["active"]]


@router.get("/membership/categories", response_model=list[CategoryOut])
def categories(_: User = Depends(_viewer), db: Session = Depends(get_db)):
    return service.categories(db)


@router.post("/membership/categories", status_code=204)
def create_category(body: CategoryIn, actor: User = Depends(_keeper), db: Session = Depends(get_db)):
    service.save_category(db, actor, body)
    return Response(status_code=204)


@router.put("/membership/categories/{category_id}", status_code=204)
def update_category(category_id: int, body: CategoryIn, actor: User = Depends(_keeper),
                    db: Session = Depends(get_db)):
    service.save_category(db, actor, body, category_id)
    return Response(status_code=204)


@router.get("/memberships/summary", response_model=MembershipSummaryOut)
def membership_summary(_: User = Depends(_viewer), db: Session = Depends(get_db)):
    return service.membership_summary(db)


@router.get("/memberships", response_model=list[MembershipOut])
def memberships(q: str | None = None, status: str | None = None, limit: int = Query(default=200, ge=1, le=200),
                _: User = Depends(_viewer), db: Session = Depends(get_db)):
    return service.memberships(db, q, status, limit)


@router.post("/memberships", response_model=MembershipOut, status_code=201)
def create_membership(body: MembershipIn, actor: User = Depends(_keeper), db: Session = Depends(get_db)):
    return service.create_membership(db, actor, body)


@router.post("/memberships/paid", response_model=MembershipOut, status_code=201)
def add_paid_member(body: PaidMemberIn, actor: User = Depends(_keeper), db: Session = Depends(get_db)):
    return service.add_paid_member(db, actor, body)


@router.post("/memberships/upload", response_model=UploadOut)
def upload_paid_members(file: UploadFile = File(), actor: User = Depends(_keeper), db: Session = Depends(get_db)):
    return service.upload_paid_members(db, actor, file.filename or "", _read(file))


@router.post("/memberships/{membership_id}/pay", status_code=204)
def pay_membership(membership_id: int, body: PayIn, actor: User = Depends(_keeper), db: Session = Depends(get_db)):
    service.pay_membership(db, actor, membership_id, body)
    return Response(status_code=204)


@router.post("/memberships/{membership_id}/{status}", status_code=204)
def set_membership_status(membership_id: int, status: Literal["waived", "cancelled"], body: ReasonIn,
                          actor: User = Depends(_keeper), db: Session = Depends(get_db)):
    service.set_membership_status(db, actor, membership_id, status, body.reason)
    return Response(status_code=204)
