from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth.deps import require
from app.core.db import get_db
from app.users import service
from app.users.models import User
from app.users.schemas import (InviteOut, ResetPasswordIn, StatusChangeIn, UserCreateIn,
                               UserCreateOut, UserOut, UserPage, UserUpdateIn)

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("", response_model=UserPage)
def list_users(q: str | None = None, status: str | None = None, user_type: str | None = "team",
               offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200),
               _: User = Depends(require("users.view")), db: Session = Depends(get_db)):
    items, total = service.list_users(db, q, status, user_type, offset, limit)
    return UserPage(items=[UserOut.model_validate(u) for u in items], total=total)


@router.post("", response_model=UserCreateOut, status_code=201)
def create_user(body: UserCreateIn, actor: User = Depends(require("users.create")),
                db: Session = Depends(get_db)):
    user, invite_url = service.create_user(db, actor, body)
    return UserCreateOut(user=UserOut.model_validate(user), invite_url=invite_url)


@router.get("/{user_id}", response_model=UserOut)
def get_user(user_id: int, _: User = Depends(require("users.view")), db: Session = Depends(get_db)):
    return service.get_user(db, user_id)


@router.patch("/{user_id}", response_model=UserOut)
def update_user(user_id: int, body: UserUpdateIn, actor: User = Depends(require("users.edit")),
                db: Session = Depends(get_db)):
    return service.update_user(db, actor, user_id, body)


@router.post("/{user_id}/reset-password", response_model=UserOut)
def reset_password(user_id: int, body: ResetPasswordIn,
                   actor: User = Depends(require("users.reset_password")),
                   db: Session = Depends(get_db)):
    return service.reset_password(db, actor, user_id, body.temp_password)


@router.post("/{user_id}/invite", response_model=InviteOut)
def reissue_invite(user_id: int, actor: User = Depends(require("users.create")),
                   db: Session = Depends(get_db)):
    return InviteOut(invite_url=service.reissue_invite(db, actor, user_id))


# Declared last so the specific /reset-password and /invite routes match first.
@router.post("/{user_id}/{action}", response_model=UserOut)
def change_status(user_id: int, action: Literal["suspend", "reactivate", "deactivate"],
                  body: StatusChangeIn, actor: User = Depends(require("users.suspend")),
                  db: Session = Depends(get_db)):
    return service.change_status(db, actor, user_id, action, body.reason)
