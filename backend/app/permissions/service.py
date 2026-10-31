"""Roles and grants, with the anti-escalation rules from docs/02-permissions.md §6."""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError, forbidden, not_found
from app.core.time import utcnow
from app.permissions import engine
from app.permissions.catalogue import CATALOGUE
from app.org.models import Department, Position
from app.permissions.engine import Scope, active_grant_filter
from app.permissions.models import Grant, PermissionAudit, Role, RolePermission
from app.permissions.schemas import GrantIn, RoleIn
from app.users.models import User

# Scope types that can be granted today. Later phases register event, folder, etc.
GRANTABLE_SCOPES = {"global", "department"}


def _can_delegate(db: Session, actor: User, code: str, scope: Scope) -> bool:
    """Delegation ceiling: you can only hand out what you hold, at no wider a scope."""
    return engine.can(db, actor, code, scope)


def _role_permission_codes(db: Session, role_id: int) -> list[str]:
    return list(db.scalars(select(RolePermission.permission_code)
                           .where(RolePermission.role_id == role_id)))


def _validate_role_permissions(db: Session, actor: User, codes: list[str]) -> list[str]:
    codes = sorted(set(codes))
    for code in codes:
        perm = CATALOGUE.get(code)
        if perm is None:
            raise AppError(422, "UNKNOWN_PERMISSION", f"Unknown permission: {code}")
        if perm.sensitive:
            raise AppError(422, "SENSITIVE_IN_ROLE",
                           f"'{code}' is sensitive and must be granted directly to a person, "
                           "not through a role.")
        if not _can_delegate(db, actor, code, engine.GLOBAL):
            raise forbidden(f"You cannot add '{code}' to a role because you do not hold it.")
    return codes


# ---------------------------------------------------------------- roles

def list_roles(db: Session) -> list[dict]:
    roles = db.scalars(select(Role).order_by(Role.name)).all()
    counts = dict(db.execute(
        select(Grant.role_id, func.count()).where(Grant.role_id.is_not(None), *active_grant_filter())
        .group_by(Grant.role_id)).all())
    return [{"id": r.id, "name": r.name, "description": r.description,
             "permissions": _role_permission_codes(db, r.id),
             "active_grant_count": counts.get(r.id, 0)} for r in roles]


def _get_role(db: Session, role_id: int) -> Role:
    role = db.get(Role, role_id)
    if role is None:
        raise not_found("Role")
    return role


def _ensure_unique_name(db: Session, name: str, exclude_id: int | None = None) -> None:
    stmt = select(Role.id).where(func.lower(Role.name) == name.lower())
    if exclude_id:
        stmt = stmt.where(Role.id != exclude_id)
    if db.scalar(stmt):
        raise AppError(409, "ROLE_NAME_TAKEN", "A role with this name already exists.")


def create_role(db: Session, actor: User, body: RoleIn) -> int:
    codes = _validate_role_permissions(db, actor, body.permissions)
    _ensure_unique_name(db, body.name)
    role = Role(name=body.name.strip(), description=body.description, created_by=actor.id)
    db.add(role)
    db.flush()
    db.add_all(RolePermission(role_id=role.id, permission_code=c) for c in codes)
    db.add(PermissionAudit(actor_id=actor.id, action="role_create", subject_type="role",
                           subject_id=role.id, role_id=role.id, reason=body.reason,
                           new_value={"name": role.name, "permissions": codes}))
    db.commit()
    return role.id


def update_role(db: Session, actor: User, role_id: int, body: RoleIn) -> None:
    role = _get_role(db, role_id)
    old_codes = _role_permission_codes(db, role_id)
    # Removing a permission is also gated by the ceiling, so nobody edits beyond their own reach.
    _validate_role_permissions(db, actor, old_codes)
    codes = _validate_role_permissions(db, actor, body.permissions)
    _ensure_unique_name(db, body.name, exclude_id=role_id)
    old = {"name": role.name, "description": role.description, "permissions": old_codes}
    role.name = body.name.strip()
    role.description = body.description
    for c in set(old_codes) - set(codes):
        db.delete(db.get(RolePermission, (role_id, c)))
    db.add_all(RolePermission(role_id=role_id, permission_code=c) for c in set(codes) - set(old_codes))
    db.add(PermissionAudit(actor_id=actor.id, action="role_update", subject_type="role",
                           subject_id=role_id, role_id=role_id, reason=body.reason, old_value=old,
                           new_value={"name": role.name, "description": role.description,
                                      "permissions": codes}))
    engine.clear_cache(db)
    db.commit()


def delete_role(db: Session, actor: User, role_id: int, reason: str) -> None:
    role = _get_role(db, role_id)
    if db.scalar(select(func.count()).select_from(Grant).where(Grant.role_id == role_id)):
        raise AppError(409, "ROLE_HAS_HISTORY",
                       "This role has been granted before, so it is kept for the record. "
                       "Revoke its grants and remove its permissions instead.")
    codes = _role_permission_codes(db, role_id)
    _validate_role_permissions(db, actor, codes)
    db.add(PermissionAudit(actor_id=actor.id, action="role_delete", subject_type="role",
                           subject_id=role_id, role_id=role_id, reason=reason,
                           old_value={"name": role.name, "permissions": codes}))
    db.delete(role)
    db.commit()


# ---------------------------------------------------------------- grants

def _grant_codes(db: Session, grant: Grant) -> list[str]:
    return [grant.permission_code] if grant.permission_code else _role_permission_codes(db, grant.role_id)


def _grant_snapshot(g: Grant) -> dict:
    return {"permission_code": g.permission_code, "role_id": g.role_id, "scope_type": g.scope_type,
            "scope_id": g.scope_id, "expires_at": g.expires_at.isoformat() if g.expires_at else None}


def _is_own_subject(db: Session, actor: User, subject_type: str, subject_id: int) -> bool:
    """True when the grant would reach the actor: themselves, a position they hold, or a
    department they belong to. Such grants are blocked so nobody can raise their own access."""
    if subject_type == "user":
        return subject_id == actor.id
    if subject_type == "position":
        return subject_id in engine.current_position_ids(db, actor.id)
    if subject_type == "department":
        return subject_id in engine.current_department_ids(db, actor.id)
    return False


def _validate_subject(db: Session, subject_type: str, subject_id: int) -> None:
    if subject_type == "user":
        target = db.get(User, subject_id)
        if target is None:
            raise not_found("User")
        if target.user_type != "team":
            raise AppError(422, "NOT_TEAM_MEMBER", "Permissions can only be granted to team accounts.")
        if target.status == "deactivated":
            raise AppError(409, "INVALID_STATE", "This account is deactivated.")
        if target.is_super_admin:
            raise AppError(409, "SUPER_ADMIN", "The Chairperson already has every permission.")
    else:
        model = Position if subject_type == "position" else Department
        target = db.get(model, subject_id)
        if target is None:
            raise not_found(subject_type.title())
        if target.status != "active":
            raise AppError(409, "INVALID_STATE", f"This {subject_type} is archived.")


def _resolve_scope(db: Session, scope_type: str, scope_id: int | None) -> Scope:
    if scope_type not in GRANTABLE_SCOPES:
        raise AppError(422, "SCOPE_NOT_AVAILABLE", f"Scope '{scope_type}' is not available yet.")
    if scope_type == "global":
        return engine.GLOBAL
    dept = db.get(Department, scope_id) if scope_id else None
    if dept is None:
        raise AppError(422, "VALIDATION_ERROR", "Choose a valid department for this grant.")
    return engine.department_scope(db, dept.id)


def create_grant(db: Session, actor: User, body: GrantIn) -> Grant:
    _validate_subject(db, body.subject_type, body.subject_id)
    if _is_own_subject(db, actor, body.subject_type, body.subject_id):
        raise forbidden("You cannot grant permissions to yourself, or to a position or department you belong to.")
    scope = _resolve_scope(db, body.scope_type, body.scope_id)
    scope_id = scope.id
    if body.expires_at is not None and body.expires_at <= utcnow():
        raise AppError(422, "VALIDATION_ERROR", "Expiry must be in the future.")

    if body.permission_code:
        perm = CATALOGUE.get(body.permission_code)
        if perm is None:
            raise AppError(422, "UNKNOWN_PERMISSION", f"Unknown permission: {body.permission_code}")
        if perm.sensitive and body.subject_type != "user":
            raise AppError(422, "SENSITIVE_NEEDS_PERSON",
                           f"'{perm.code}' is sensitive and can only be granted to a named person.")
        codes = [body.permission_code]
    else:
        _get_role(db, body.role_id)
        codes = _role_permission_codes(db, body.role_id)
    for code in codes:
        if not _can_delegate(db, actor, code, scope):
            raise forbidden(f"You cannot grant '{code}' because you do not hold it at this scope.")

    duplicate = db.scalar(select(Grant.id).where(
        Grant.subject_type == body.subject_type, Grant.subject_id == body.subject_id,
        Grant.permission_code.is_not_distinct_from(body.permission_code),
        Grant.role_id.is_not_distinct_from(body.role_id),
        Grant.scope_type == body.scope_type,
        Grant.scope_id.is_not_distinct_from(scope_id),
        *active_grant_filter()))
    if duplicate:
        raise AppError(409, "DUPLICATE_GRANT", "This grant already exists.")

    grant = Grant(subject_type=body.subject_type, subject_id=body.subject_id,
                  permission_code=body.permission_code, role_id=body.role_id,
                  scope_type=body.scope_type, scope_id=scope_id, expires_at=body.expires_at,
                  granted_by=actor.id, reason=body.reason)
    db.add(grant)
    db.flush()
    db.add(PermissionAudit(actor_id=actor.id, action="grant", subject_type=body.subject_type,
                           subject_id=body.subject_id, permission_code=body.permission_code,
                           role_id=body.role_id, scope_type=body.scope_type, scope_id=scope_id,
                           new_value={**_grant_snapshot(grant), "grant_id": grant.id},
                           reason=body.reason))
    engine.clear_cache(db)
    db.commit()
    return grant


def revoke_grant(db: Session, actor: User, grant_id: int, reason: str) -> Grant:
    grant = db.get(Grant, grant_id)
    if grant is None:
        raise not_found("Grant")
    if grant.revoked_at is not None:
        raise AppError(409, "ALREADY_REVOKED", "This grant has already been revoked.")
    if _is_own_subject(db, actor, grant.subject_type, grant.subject_id):
        raise forbidden("You cannot change your own permissions.")
    scope = (engine.department_scope(db, grant.scope_id) if grant.scope_type == "department"
             else Scope(grant.scope_type, grant.scope_id))
    for code in _grant_codes(db, grant):
        if not _can_delegate(db, actor, code, scope):
            raise forbidden(f"You cannot revoke '{code}' because you do not hold it at this scope.")
    grant.revoked_at = utcnow()
    grant.revoked_by = actor.id
    db.add(PermissionAudit(actor_id=actor.id, action="revoke", subject_type=grant.subject_type,
                           subject_id=grant.subject_id, permission_code=grant.permission_code,
                           role_id=grant.role_id, scope_type=grant.scope_type,
                           scope_id=grant.scope_id,
                           old_value={**_grant_snapshot(grant), "grant_id": grant.id},
                           reason=reason))
    engine.clear_cache(db)
    db.commit()
    return grant


def list_grants(db: Session, subject_type: str, subject_id: int, include_inactive: bool,
                grant_id: int | None = None) -> list[dict]:
    stmt = select(Grant).where(Grant.subject_type == subject_type, Grant.subject_id == subject_id)
    if grant_id is not None:
        stmt = stmt.where(Grant.id == grant_id)
    elif not include_inactive:
        stmt = stmt.where(*active_grant_filter())
    grants = db.scalars(stmt.order_by(Grant.created_at.desc())).all()
    names = dict(db.execute(select(User.id, User.full_name)
                            .where(User.id.in_({g.granted_by for g in grants}))).all())
    roles = dict(db.execute(select(Role.id, Role.name)
                            .where(Role.id.in_({g.role_id for g in grants if g.role_id}))).all())
    depts = dict(db.execute(select(Department.id, Department.name).where(Department.id.in_(
        {g.scope_id for g in grants if g.scope_type == "department"}))).all())
    now = utcnow()
    return [{"id": g.id, "subject_type": g.subject_type, "subject_id": g.subject_id,
             "permission_code": g.permission_code,
             "role_id": g.role_id, "role_name": roles.get(g.role_id), "scope_type": g.scope_type,
             "scope_id": g.scope_id, "scope_name": depts.get(g.scope_id) if g.scope_type == "department" else None,
             "expires_at": g.expires_at, "revoked_at": g.revoked_at,
             "granted_by": g.granted_by, "granted_by_name": names.get(g.granted_by),
             "reason": g.reason, "created_at": g.created_at,
             "active": g.revoked_at is None and (g.expires_at is None or g.expires_at > now)}
            for g in grants]


def expire_grants(db: Session) -> int:
    """Nightly job: mark lapsed grants and write an 'expire' audit row for each."""
    now = utcnow()
    lapsed = db.scalars(select(Grant).where(Grant.revoked_at.is_(None),
                                            Grant.expires_at.is_not(None),
                                            Grant.expires_at <= now)).all()
    for g in lapsed:
        g.revoked_at = g.expires_at
        db.add(PermissionAudit(actor_id=None, action="expire", subject_type=g.subject_type,
                               subject_id=g.subject_id, permission_code=g.permission_code,
                               role_id=g.role_id, scope_type=g.scope_type, scope_id=g.scope_id,
                               old_value={**_grant_snapshot(g), "grant_id": g.id},
                               reason="Grant reached its expiry date"))
    db.commit()
    return len(lapsed)
