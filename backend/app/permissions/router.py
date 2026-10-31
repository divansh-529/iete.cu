from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased

from app.auth.deps import require
from app.core.db import get_db
from app.core.errors import not_found
from app.permissions import service
from app.permissions.engine import effective_grants
from app.permissions.catalogue import CATALOGUE
from app.org.models import Department, Position
from app.permissions.models import Permission, PermissionAudit, Role
from app.permissions.schemas import (EffectiveAccessOut, EffectiveOut, GrantIn, GrantOut,
                                     PermissionAuditOut, PermissionOut, RevokeIn, RoleIn, RoleOut)
from app.users.models import User

router = APIRouter(prefix="/api", tags=["permissions"])


@router.get("/permissions", response_model=list[PermissionOut])
def list_permissions(_: User = Depends(require("permissions.view")), db: Session = Depends(get_db)):
    return db.scalars(select(Permission).order_by(Permission.module, Permission.code)).all()


@router.get("/roles", response_model=list[RoleOut])
def list_roles(_: User = Depends(require("permissions.view")), db: Session = Depends(get_db)):
    return service.list_roles(db)


@router.post("/roles", response_model=RoleOut, status_code=201)
def create_role(body: RoleIn, actor: User = Depends(require("roles.manage")),
                db: Session = Depends(get_db)):
    role_id = service.create_role(db, actor, body)
    return next(r for r in service.list_roles(db) if r["id"] == role_id)


@router.put("/roles/{role_id}", response_model=RoleOut)
def update_role(role_id: int, body: RoleIn, actor: User = Depends(require("roles.manage")),
                db: Session = Depends(get_db)):
    service.update_role(db, actor, role_id, body)
    return next(r for r in service.list_roles(db) if r["id"] == role_id)


@router.delete("/roles/{role_id}", status_code=204)
def delete_role(role_id: int, reason: str = Query(min_length=3, max_length=500),
                actor: User = Depends(require("roles.manage")), db: Session = Depends(get_db)):
    service.delete_role(db, actor, role_id, reason)


@router.get("/grants", response_model=list[GrantOut])
def list_grants(subject_type: Literal["user", "position", "department"], subject_id: int,
                include_inactive: bool = False,
                _: User = Depends(require("permissions.view")), db: Session = Depends(get_db)):
    return service.list_grants(db, subject_type, subject_id, include_inactive)


@router.post("/grants", response_model=GrantOut, status_code=201)
def create_grant(body: GrantIn, actor: User = Depends(require("permissions.manage")),
                 db: Session = Depends(get_db)):
    grant = service.create_grant(db, actor, body)
    return service.list_grants(db, grant.subject_type, grant.subject_id, True, grant.id)[0]


@router.post("/grants/{grant_id}/revoke", response_model=GrantOut)
def revoke_grant(grant_id: int, body: RevokeIn, actor: User = Depends(require("permissions.manage")),
                 db: Session = Depends(get_db)):
    grant = service.revoke_grant(db, actor, grant_id, body.reason)
    return service.list_grants(db, grant.subject_type, grant.subject_id, True, grant.id)[0]


@router.get("/grants/effective", response_model=EffectiveAccessOut)
def effective_access(user_id: int, _: User = Depends(require("permissions.view")),
                     db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user is None:
        raise not_found("User")
    if user.is_super_admin:
        return EffectiveAccessOut(all_permissions=True, permissions=[])
    perms = [EffectiveOut(code=g.permission, scope_type=g.scope_type, scope_id=g.scope_id,
                          via_role=g.via_role, via_subject=g.via_subject, grant_id=g.grant_id)
             for g in effective_grants(db, user)
             if not (CATALOGUE[g.permission].sensitive and not g.direct)]
    return EffectiveAccessOut(all_permissions=False, permissions=perms)


@router.get("/permission-audit", response_model=list[PermissionAuditOut])
def permission_audit(subject_id: int | None = None, before_id: int | None = None,
                     limit: int = Query(50, ge=1, le=200),
                     _: User = Depends(require("audit.view")), db: Session = Depends(get_db)):
    actor = aliased(User)
    subject = aliased(User)
    subject_name = func.coalesce(subject.full_name, Position.title, Department.name, Role.name)
    stmt = (select(PermissionAudit, actor.full_name, subject_name)
            .outerjoin(actor, actor.id == PermissionAudit.actor_id)
            .outerjoin(subject, (subject.id == PermissionAudit.subject_id)
                       & (PermissionAudit.subject_type == "user"))
            .outerjoin(Position, (Position.id == PermissionAudit.subject_id)
                       & (PermissionAudit.subject_type == "position"))
            .outerjoin(Department, (Department.id == PermissionAudit.subject_id)
                       & (PermissionAudit.subject_type == "department"))
            .outerjoin(Role, (Role.id == PermissionAudit.subject_id)
                       & (PermissionAudit.subject_type == "role")))
    if subject_id is not None:
        stmt = stmt.where(PermissionAudit.subject_type == "user",
                          PermissionAudit.subject_id == subject_id)
    if before_id is not None:
        stmt = stmt.where(PermissionAudit.id < before_id)
    rows = db.execute(stmt.order_by(PermissionAudit.id.desc()).limit(limit)).all()
    return [PermissionAuditOut(**{c: getattr(pa, c) for c in PermissionAuditOut.model_fields
                                  if hasattr(pa, c)},
                               actor_name=actor_name, subject_name=subject_name)
            for pa, actor_name, subject_name in rows]
