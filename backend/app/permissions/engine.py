"""Access checks. Every protected endpoint goes through `can()`: directly via the `require()`
dependency, or via `ensure()` in services when the scope depends on the record being touched.

Deny by default. A grant applies when it is active (not revoked, not expired), its subject is
the user or a position/department the user currently holds, it names the permission directly
or through a role, and its scope covers the requested scope.
"""
from dataclasses import dataclass, field

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.core.errors import forbidden
from app.core.time import utcnow
from app.org.models import Department, DepartmentMembership, Position, PositionAssignment
from app.permissions.catalogue import CATALOGUE
from app.permissions.models import Grant, Role, RolePermission
from app.users.models import User


@dataclass(frozen=True)
class Scope:
    type: str = "global"
    id: int | None = None
    # Containing scopes, e.g. a sub-department's parent. Grants on a parent cover the child.
    parents: tuple["Scope", ...] = field(default=())


GLOBAL = Scope()


def covers(grant_scope_type: str, grant_scope_id: int | None, scope: Scope) -> bool:
    if grant_scope_type == "global":
        return True
    if scope.type == grant_scope_type and scope.id == grant_scope_id:
        return True
    return any(covers(grant_scope_type, grant_scope_id, p) for p in scope.parents)


def department_scope(db: Session, department_id: int | None) -> Scope:
    """Scope for a department, including its ancestors. None means organisation-wide."""
    if department_id is None:
        return GLOBAL
    chain: list[int] = []
    current: int | None = department_id
    while current is not None and current not in chain:
        chain.append(current)
        current = db.scalar(select(Department.parent_id).where(Department.id == current))
    scope = None
    for dept_id in reversed(chain):
        scope = Scope("department", dept_id, (scope,) if scope else ())
    return scope  # type: ignore[return-value]


@dataclass(frozen=True)
class EffectiveGrant:
    permission: str
    scope_type: str
    scope_id: int | None
    grant_id: int
    via_role: str | None = None      # role name when inherited through a role
    via_subject: str | None = None   # e.g. "position: Ops Lead" when not granted to the user directly

    @property
    def direct(self) -> bool:
        return self.via_role is None and self.via_subject is None


_CACHE_KEY = "effective_grants"


def active_grant_filter():
    return (Grant.revoked_at.is_(None),
            or_(Grant.expires_at.is_(None), Grant.expires_at > utcnow()))


def current_position_ids(db: Session, user_id: int) -> set[int]:
    return set(db.scalars(select(PositionAssignment.position_id).where(
        PositionAssignment.user_id == user_id, PositionAssignment.valid_to.is_(None))))


def current_department_ids(db: Session, user_id: int) -> set[int]:
    return set(db.scalars(select(DepartmentMembership.department_id).where(
        DepartmentMembership.user_id == user_id, DepartmentMembership.valid_to.is_(None))))


def effective_grants(db: Session, user: User) -> list[EffectiveGrant]:
    cache = db.info.setdefault(_CACHE_KEY, {})
    if user.id in cache:
        return cache[user.id]

    position_ids = current_position_ids(db, user.id)
    department_ids = current_department_ids(db, user.id)
    subjects = [and_(Grant.subject_type == "user", Grant.subject_id == user.id)]
    if position_ids:
        subjects.append(and_(Grant.subject_type == "position", Grant.subject_id.in_(position_ids)))
    if department_ids:
        subjects.append(and_(Grant.subject_type == "department", Grant.subject_id.in_(department_ids)))
    grants = db.scalars(select(Grant).where(or_(*subjects), *active_grant_filter())).all()

    position_names = dict(db.execute(select(Position.id, Position.title)
                                     .where(Position.id.in_(position_ids))).all()) if position_ids else {}
    department_names = dict(db.execute(select(Department.id, Department.name)
                                       .where(Department.id.in_(department_ids))).all()) if department_ids else {}

    role_ids = {g.role_id for g in grants if g.role_id}
    role_perms: dict[int, list[str]] = {rid: [] for rid in role_ids}
    role_names: dict[int, str] = {}
    if role_ids:
        for rp in db.scalars(select(RolePermission).where(RolePermission.role_id.in_(role_ids))):
            role_perms[rp.role_id].append(rp.permission_code)
        role_names = dict(db.execute(select(Role.id, Role.name).where(Role.id.in_(role_ids))).all())

    result: list[EffectiveGrant] = []
    for g in grants:
        via_subject = None
        if g.subject_type == "position":
            via_subject = f"position: {position_names.get(g.subject_id, g.subject_id)}"
        elif g.subject_type == "department":
            via_subject = f"department: {department_names.get(g.subject_id, g.subject_id)}"
        if g.permission_code:
            result.append(EffectiveGrant(g.permission_code, g.scope_type, g.scope_id, g.id,
                                         via_subject=via_subject))
        else:
            for code in role_perms.get(g.role_id, []):
                result.append(EffectiveGrant(code, g.scope_type, g.scope_id, g.id,
                                             via_role=role_names.get(g.role_id), via_subject=via_subject))
    cache[user.id] = result
    return result


def clear_cache(db: Session) -> None:
    db.info.pop(_CACHE_KEY, None)


def _usable(db: Session, user: User, permission: str) -> list[EffectiveGrant] | None:
    """None = everything (super admin); [] = nothing; otherwise the grants that can be used."""
    perm = CATALOGUE.get(permission)
    if perm is None:
        raise ValueError(f"Unknown permission code: {permission}")
    if user.status != "active":
        return []
    if user.is_super_admin:
        return None
    return [g for g in effective_grants(db, user) if g.permission == permission
            and (g.direct or not perm.sensitive)]   # sensitive ⇒ direct grant only


def can(db: Session, user: User, permission: str, scope: Scope = GLOBAL) -> bool:
    grants = _usable(db, user, permission)
    return grants is None or any(covers(g.scope_type, g.scope_id, scope) for g in grants)


def ensure(db: Session, user: User, permission: str, scope: Scope = GLOBAL) -> None:
    if not can(db, user, permission, scope):
        raise forbidden()


def has_any(db: Session, user: User, permission: str) -> bool:
    """True if the user holds the permission at any scope (coarse gate before a scoped check)."""
    grants = _usable(db, user, permission)
    return grants is None or bool(grants)


def users_who_can(db: Session, permission: str, scope: Scope, exclude: set[int] = frozenset()) -> list[int]:
    """Active team members who hold `permission` at `scope` (used to notify reviewers and
    approvers). Checks each person, which is fine for a forum-sized team."""
    users = db.scalars(select(User).where(User.user_type == "team", User.status == "active",
                                          User.id.not_in(exclude or {0}))).all()
    return [u.id for u in users if can(db, u, permission, scope)]


def visible_department_ids(db: Session, user: User, permission: str) -> set[int] | None:
    """Departments where the user holds `permission` (including sub-departments).
    None means every department (a global grant)."""
    grants = _usable(db, user, permission)
    if grants is None or any(g.scope_type == "global" for g in grants):
        return None
    roots = {g.scope_id for g in grants if g.scope_type == "department"}
    children: dict[int, list[int]] = {}
    for dept_id, parent_id in db.execute(select(Department.id, Department.parent_id)).all():
        if parent_id is not None:
            children.setdefault(parent_id, []).append(dept_id)
    result, stack = set(), list(roots)
    while stack:
        d = stack.pop()
        if d not in result:
            result.add(d)
            stack.extend(children.get(d, []))
    return result
