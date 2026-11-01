"""Who may see the society's membership list (the Chairperson's rule). It goes by the position held,
not by grants, so it can't spread through a role or a stray permission: the Joint Secretary, Secretary,
Vice Chairperson and Chairperson see it, and the Treasurer, who keeps it, sees and changes it."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.org.models import Position, PositionAssignment
from app.users.models import User

VIEWER_POSITIONS = {"Joint Secretary", "Secretary", "Vice Chairperson", "Chairperson"}
KEEPER_POSITION = "Treasurer"


def _titles(db: Session, user: User) -> set[str]:
    return set(db.scalars(select(Position.title).join(PositionAssignment, PositionAssignment.position_id == Position.id).where(
        PositionAssignment.user_id == user.id, PositionAssignment.valid_to.is_(None), Position.status == "active")))


def can_record_members(db: Session, user: User) -> bool:
    return user.is_super_admin or KEEPER_POSITION in _titles(db, user)


def can_view_members(db: Session, user: User) -> bool:
    return user.is_super_admin or bool(_titles(db, user) & (VIEWER_POSITIONS | {KEEPER_POSITION}))
