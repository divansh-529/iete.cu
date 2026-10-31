from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.models import AuditEvent
from app.auth.deps import require
from app.core.db import get_db
from app.users.models import User

router = APIRouter(prefix="/api/audit", tags=["audit"])


class AuditEventOut(BaseModel):
    id: int
    actor_id: int | None
    actor_name: str | None
    action: str
    entity_type: str
    entity_id: int | None
    before: dict | None
    after: dict | None
    ip: str | None
    created_at: datetime


@router.get("", response_model=list[AuditEventOut])
def list_audit(entity_type: str | None = None, entity_id: int | None = None,
               actor_id: int | None = None, action: str | None = None,
               before_id: int | None = None, limit: int = Query(50, ge=1, le=200),
               _: User = Depends(require("audit.view")), db: Session = Depends(get_db)):
    stmt = select(AuditEvent, User.full_name).outerjoin(User, User.id == AuditEvent.actor_id)
    if entity_type:
        stmt = stmt.where(AuditEvent.entity_type == entity_type)
    if entity_id is not None:
        stmt = stmt.where(AuditEvent.entity_id == entity_id)
    if actor_id is not None:
        stmt = stmt.where(AuditEvent.actor_id == actor_id)
    if action:
        stmt = stmt.where(AuditEvent.action.startswith(action))
    if before_id is not None:
        stmt = stmt.where(AuditEvent.id < before_id)
    rows = db.execute(stmt.order_by(AuditEvent.id.desc()).limit(limit)).all()
    return [AuditEventOut(id=e.id, actor_id=e.actor_id, actor_name=name, action=e.action,
                          entity_type=e.entity_type, entity_id=e.entity_id, before=e.before,
                          after=e.after, ip=str(e.ip) if e.ip else None, created_at=e.created_at)
            for e, name in rows]
