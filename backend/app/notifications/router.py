from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.auth.deps import current_user
from app.core.db import get_db
from app.notifications import service
from app.users.models import User

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    payload: dict
    read_at: datetime | None
    created_at: datetime


class NotificationPage(BaseModel):
    items: list[NotificationOut]
    unread: int


class MarkReadIn(BaseModel):
    ids: list[int] | None = None     # None = all


@router.get("", response_model=NotificationPage)
def my_notifications(limit: int = Query(30, ge=1, le=100), user: User = Depends(current_user),
                     db: Session = Depends(get_db)):
    items, unread = service.list_for(db, user.id, limit)
    return {"items": items, "unread": unread}


@router.post("/read", status_code=204)
def mark_read(body: MarkReadIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    service.mark_read(db, user.id, body.ids)
