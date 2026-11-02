"""Finance and membership powers that go by the position held. They can't spread through a role or a
stray permission, and they end when the person leaves the position.

The Joint Secretary, Secretary, Vice Chairperson and Chairperson see the society's membership list. The
Treasurer and Joint Secretary are the keepers: they keep that list and manage finances, but what they
record waits for the Chairperson before it counts in a balance (the Chairperson's rule)."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.org.models import Position, PositionAssignment
from app.permissions.engine import GLOBAL, Scope, can
from app.users.models import User

VIEWER_POSITIONS = {"Joint Secretary", "Secretary", "Vice Chairperson", "Chairperson"}
KEEPER_POSITIONS = {"Treasurer", "Joint Secretary"}
# Not finance.expense.approve: approving and reversing stay with approvers.
KEEPER_PERMISSIONS = {"finance.view", "finance.income.record", "finance.expense.submit", "finance.expense.verify",
                      "finance.accounts.manage", "finance.reconcile"}


def _titles(db: Session, user: User) -> set[str]:
    return set(db.scalars(select(Position.title).join(PositionAssignment, PositionAssignment.position_id == Position.id).where(
        PositionAssignment.user_id == user.id, PositionAssignment.valid_to.is_(None), Position.status == "active")))


def is_keeper(db: Session, user: User) -> bool:
    return not user.is_super_admin and bool(_titles(db, user) & KEEPER_POSITIONS)


def finance_can(db: Session, user: User, permission: str, scope: Scope = GLOBAL) -> bool:
    if permission in KEEPER_PERMISSIONS and user.status == "active" and is_keeper(db, user):
        return True
    return can(db, user, permission, scope)


def can_record_members(db: Session, user: User) -> bool:
    return user.is_super_admin or bool(_titles(db, user) & KEEPER_POSITIONS)


def can_view_members(db: Session, user: User) -> bool:
    return user.is_super_admin or bool(_titles(db, user) & (VIEWER_POSITIONS | KEEPER_POSITIONS))
