"""Departments, positions, assignments, memberships, profiles and terms.

Rules (docs/03-data-model.md §1): assignments and memberships are closed, never edited or
deleted, so the history of who held which role stays answerable. Moving someone off a
position immediately removes any access granted to that position.
"""
from datetime import date

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit import service as audit
from app.core.errors import AppError, forbidden, not_found
from app.core.time import utcnow
from app.permissions import engine
from app.permissions.engine import department_scope, ensure
from app.org.models import (Department, DepartmentMembership, MemberProfile, Position,
                            PositionAssignment, Term)
from app.org.schemas import (AssignIn, DepartmentIn, EndAssignmentIn, MemberIn, PositionIn, ProfileIn,
                             SelfProfileIn, TermIn, TransferIn)
from app.users.models import User


def _today() -> date:
    return date.today()


def _person(u: User) -> dict:
    return {"id": u.id, "full_name": u.full_name, "email": u.email}


def people_by_id(db: Session, ids) -> dict[int, dict]:
    """PersonRef dicts for the given user ids (missing ids are skipped)."""
    wanted = {i for i in ids if i}
    if not wanted:
        return {}
    return {u.id: _person(u) for u in db.scalars(select(User).where(User.id.in_(wanted)))}


def department_names(db: Session, ids) -> dict[int, str]:
    wanted = {i for i in ids if i}
    if not wanted:
        return {}
    return dict(db.execute(select(Department.id, Department.name).where(Department.id.in_(wanted))).all())


def active_team_user(db: Session, user_id: int) -> User:
    """A team account that can be given work (assigned, added to an event team)."""
    return _active_user(db, user_id)


# ---------------------------------------------------------------- lookups

def get_department(db: Session, dept_id: int) -> Department:
    dept = db.get(Department, dept_id)
    if dept is None or dept.status == "deleted":
        raise not_found("Department")
    return dept


def get_position(db: Session, position_id: int) -> Position:
    pos = db.get(Position, position_id)
    if pos is None or pos.status == "deleted":
        raise not_found("Position")
    return pos


def _scope_for_position(db: Session, pos: Position) -> engine.Scope:
    return department_scope(db, pos.department_id)


def _ensure_can_staff(db: Session, actor: User, pos: Position) -> None:
    """Filling or vacating a position needs org.assign. For a lead or deputy seat it also needs
    org.manage, so a department lead can staff their team with members but never make (or
    unmake) another lead."""
    scope = _scope_for_position(db, pos)
    ensure(db, actor, "org.assign", scope)
    if (pos.is_lead or pos.is_deputy) and not engine.can(db, actor, "org.manage", scope):
        raise forbidden("Only an administrator can appoint or remove leads and deputies.")


def _active_user(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise not_found("User")
    if user.user_type != "team" or user.status not in ("active", "invited"):
        raise AppError(409, "INVALID_STATE", "Only active team accounts can be given roles or departments.")
    return user


def _open_holders(db: Session, position_ids: list[int]) -> dict[int, list[tuple[PositionAssignment, User]]]:
    result: dict[int, list] = {pid: [] for pid in position_ids}
    if not position_ids:
        return result
    rows = db.execute(select(PositionAssignment, User).join(User, User.id == PositionAssignment.user_id)
                      .where(PositionAssignment.position_id.in_(position_ids),
                             PositionAssignment.valid_to.is_(None))
                      .order_by(PositionAssignment.valid_from)).all()
    for pa, user in rows:
        result[pa.position_id].append((pa, user))
    return result


# ---------------------------------------------------------------- departments

def _check_no_cycle_department(db: Session, dept_id: int | None, new_parent: int | None) -> None:
    current = new_parent
    seen = set()
    while current is not None:
        if current == dept_id or current in seen:
            raise AppError(422, "CYCLE", "A department cannot sit inside itself.")
        seen.add(current)
        current = db.scalar(select(Department.parent_id).where(Department.id == current))


def _dept_snapshot(d: Department) -> dict:
    return {"name": d.name, "description": d.description, "parent_id": d.parent_id, "status": d.status}


def department_summaries(db: Session, visible: set[int] | None, include_archived: bool) -> list[dict]:
    stmt = select(Department).where(Department.status != "deleted").order_by(Department.name)
    if not include_archived:
        stmt = stmt.where(Department.status == "active")
    if visible is not None:
        stmt = stmt.where(Department.id.in_(visible))
    depts = db.scalars(stmt).all()
    ids = [d.id for d in depts]
    members = dict(db.execute(select(DepartmentMembership.department_id, func.count())
                              .where(DepartmentMembership.department_id.in_(ids),
                                     DepartmentMembership.valid_to.is_(None))
                              .group_by(DepartmentMembership.department_id)).all())
    positions = db.scalars(select(Position).where(Position.department_id.in_(ids),
                                                  Position.status == "active")).all()
    holders = _open_holders(db, [p.id for p in positions])
    out = []
    for d in depts:
        dept_positions = [p for p in positions if p.department_id == d.id]
        out.append({
            "id": d.id, "name": d.name, "description": d.description, "parent_id": d.parent_id,
            "status": d.status, "member_count": members.get(d.id, 0),
            "position_count": len(dept_positions),
            "vacant_positions": sum(1 for p in dept_positions if not holders[p.id] and not p.is_category),
            "leads": [_person(u) for p in dept_positions if p.is_lead for _, u in holders[p.id]],
        })
    return out


def create_department(db: Session, actor: User, body: DepartmentIn) -> Department:
    if body.parent_id is not None:
        get_department(db, body.parent_id)
    ensure(db, actor, "org.manage", department_scope(db, body.parent_id))
    dept = Department(name=body.name.strip(), description=body.description,
                      parent_id=body.parent_id, created_by=actor.id)
    db.add(dept)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise AppError(409, "NAME_TAKEN", "A department with this name already exists.")
    audit.record(db, actor.id, "department.create", "department", dept.id, after=_dept_snapshot(dept))
    db.commit()
    return dept


def update_department(db: Session, actor: User, dept_id: int, body: DepartmentIn) -> Department:
    dept = get_department(db, dept_id)
    ensure(db, actor, "org.manage", department_scope(db, dept.id))
    if body.parent_id != dept.parent_id:
        if body.parent_id is not None:
            get_department(db, body.parent_id)
        _check_no_cycle_department(db, dept.id, body.parent_id)
        ensure(db, actor, "org.manage", department_scope(db, body.parent_id))
    before = _dept_snapshot(dept)
    dept.name = body.name.strip()
    dept.description = body.description
    dept.parent_id = body.parent_id
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise AppError(409, "NAME_TAKEN", "A department with this name already exists.")
    audit.record(db, actor.id, "department.update", "department", dept.id, before=before,
                 after=_dept_snapshot(dept))
    engine.clear_cache(db)
    db.commit()
    return dept


def set_department_status(db: Session, actor: User, dept_id: int, archive: bool, reason: str) -> Department:
    dept = get_department(db, dept_id)
    ensure(db, actor, "org.manage", department_scope(db, dept.parent_id))
    if archive:
        if dept.status == "archived":
            raise AppError(409, "INVALID_STATE", "This department is already archived.")
        open_members = db.scalar(select(func.count()).select_from(DepartmentMembership).where(
            DepartmentMembership.department_id == dept.id, DepartmentMembership.valid_to.is_(None)))
        held = db.scalar(select(func.count()).select_from(PositionAssignment)
                         .join(Position, Position.id == PositionAssignment.position_id)
                         .where(Position.department_id == dept.id, PositionAssignment.valid_to.is_(None)))
        children = db.scalar(select(func.count()).select_from(Department).where(
            Department.parent_id == dept.id, Department.status == "active"))
        if open_members or held or children:
            raise AppError(409, "DEPARTMENT_IN_USE",
                           "Move its members, end its position assignments and archive its "
                           "sub-departments before archiving it.")
    elif dept.status == "active":
        raise AppError(409, "INVALID_STATE", "This department is already active.")
    before = _dept_snapshot(dept)
    dept.status = "archived" if archive else "active"
    if archive:
        db.execute(update(Position).where(Position.department_id == dept.id, Position.status != "deleted")
                   .values(status="archived"))
    audit.record(db, actor.id, "department.archive" if archive else "department.restore",
                 "department", dept.id, before=before, after={**_dept_snapshot(dept), "reason": reason})
    db.commit()
    return dept


def delete_department(db: Session, actor: User, dept_id: int, reason: str, confirm_name: str) -> dict:
    """The Chairperson removes a department outright, even while it is in use: everyone is taken
    out, its positions are vacated and closed, access given through it is revoked, pending recruits
    are declined and sub-departments move up a level. The department then disappears for good.

    The row itself is kept as 'deleted' (not erased) so past memberships, events and the audit log
    still say which department it was, as the Chairperson's record-keeping rule requires."""
    from app.members.models import MemberProposal
    from app.permissions.models import Grant, PermissionAudit

    if not actor.is_super_admin:
        raise forbidden("Only the Chairperson can delete a department.")
    dept = get_department(db, dept_id)
    if confirm_name.strip().lower() != dept.name.lower():
        raise AppError(422, "CONFIRMATION_MISMATCH", f"Type the department's name, “{dept.name}”, to confirm.")
    now, today = utcnow(), _today()
    summary = {"members_removed": 0, "positions_closed": 0, "grants_revoked": 0, "proposals_declined": 0,
               "subdepartments_moved": 0}

    for pos in db.scalars(select(Position).where(Position.department_id == dept.id, Position.status != "deleted")):
        for pa, _ in _open_holders(db, [pos.id])[pos.id]:
            _close_assignment(db, actor, pa, max(today, pa.valid_from), "removed", f"{dept.name} was deleted")
        if pos.status == "active":
            summary["positions_closed"] += 1
        pos.status = "archived"
        db.execute(update(Position).where(Position.reports_to_position_id == pos.id)
                   .values(reports_to_position_id=pos.reports_to_position_id))
    for m in db.scalars(select(DepartmentMembership).where(DepartmentMembership.department_id == dept.id,
                                                           DepartmentMembership.valid_to.is_(None))):
        m.valid_to, m.end_reason, m.ended_by = max(today, m.valid_from), "Department deleted", actor.id
        summary["members_removed"] += 1
    # Access given to the department, to its positions, or limited to it, all ends now.
    position_ids = list(db.scalars(select(Position.id).where(Position.department_id == dept.id)))
    grants = db.scalars(select(Grant).where(
        Grant.revoked_at.is_(None),
        ((Grant.subject_type == "department") & (Grant.subject_id == dept.id))
        | ((Grant.scope_type == "department") & (Grant.scope_id == dept.id))
        | ((Grant.subject_type == "position") & Grant.subject_id.in_(position_ids or [0])))).all()
    for g in grants:
        g.revoked_at, g.revoked_by = now, actor.id
        db.add(PermissionAudit(actor_id=actor.id, action="revoke", subject_type=g.subject_type,
                               subject_id=g.subject_id, permission_code=g.permission_code, role_id=g.role_id,
                               scope_type=g.scope_type, scope_id=g.scope_id, old_value={"grant_id": g.id},
                               reason=f"Department deleted: {reason}"))
        summary["grants_revoked"] += 1
    for p in db.scalars(select(MemberProposal).where(MemberProposal.department_id == dept.id,
                                                     MemberProposal.status == "pending")):
        p.status, p.decided_by, p.decided_at = "rejected", actor.id, now
        p.decision_remarks = f"{dept.name} was deleted"
        candidate = db.get(User, p.user_id)
        if candidate.status == "proposed":
            candidate.status = "rejected"
        summary["proposals_declined"] += 1
    for child in db.scalars(select(Department).where(Department.parent_id == dept.id, Department.status != "deleted")):
        child.parent_id = dept.parent_id
        summary["subdepartments_moved"] += 1

    before = _dept_snapshot(dept)
    dept.status = "deleted"
    audit.record(db, actor.id, "department.delete", "department", dept.id, before=before,
                 after={**_dept_snapshot(dept), "reason": reason, **summary})
    engine.clear_cache(db)
    db.commit()
    return summary


# ---------------------------------------------------------------- positions

def _check_no_cycle_position(db: Session, position_id: int | None, reports_to: int | None) -> None:
    current = reports_to
    seen = set()
    while current is not None:
        if current == position_id or current in seen:
            raise AppError(422, "CYCLE", "This reporting line would loop back on itself.")
        seen.add(current)
        current = db.scalar(select(Position.reports_to_position_id).where(Position.id == current))


def _pos_snapshot(p: Position) -> dict:
    return {"title": p.title, "department_id": p.department_id,
            "reports_to_position_id": p.reports_to_position_id, "is_lead": p.is_lead,
            "is_deputy": p.is_deputy, "is_category": p.is_category, "max_holders": p.max_holders, "status": p.status}


def position_views(db: Session, positions: list[Position]) -> list[dict]:
    holders = _open_holders(db, [p.id for p in positions])
    dept_names = dict(db.execute(select(Department.id, Department.name).where(
        Department.id.in_({p.department_id for p in positions if p.department_id}))).all())
    return [{
        "id": p.id, "title": p.title, "description": p.description, "department_id": p.department_id,
        "department_name": dept_names.get(p.department_id), "reports_to_position_id": p.reports_to_position_id,
        "is_lead": p.is_lead, "is_deputy": p.is_deputy, "is_category": p.is_category, "max_holders": p.max_holders,
        "rank_order": p.rank_order, "status": p.status,
        "holders": [{"assignment_id": pa.id, "user": _person(u), "valid_from": pa.valid_from}
                    for pa, u in holders[p.id]],
    } for p in positions]


def list_positions(db: Session, visible: set[int] | None, department_id: int | None,
                   leadership_only: bool, include_archived: bool) -> list[Position]:
    stmt = select(Position).where(Position.status != "deleted").order_by(Position.rank_order, Position.title)
    if not include_archived:
        stmt = stmt.where(Position.status == "active")
    if leadership_only:
        stmt = stmt.where(Position.department_id.is_(None))
    elif department_id is not None:
        stmt = stmt.where(Position.department_id == department_id)
    if visible is not None:
        stmt = stmt.where(Position.department_id.in_(visible))
    return list(db.scalars(stmt))


def _validate_position_links(db: Session, body: PositionIn, position_id: int | None) -> None:
    if body.is_category and (body.is_lead or body.is_deputy):
        raise AppError(422, "INVALID_CATEGORY", "A category can't also be a lead or deputy.")
    if body.department_id is not None and get_department(db, body.department_id).status != "active":
        raise AppError(409, "INVALID_STATE", "That department is archived.")
    if body.reports_to_position_id is not None:
        get_position(db, body.reports_to_position_id)
        _check_no_cycle_position(db, position_id, body.reports_to_position_id)


def create_position(db: Session, actor: User, body: PositionIn) -> Position:
    _validate_position_links(db, body, None)
    ensure(db, actor, "org.manage", department_scope(db, body.department_id))
    pos = Position(**body.model_dump())
    db.add(pos)
    db.flush()
    audit.record(db, actor.id, "position.create", "position", pos.id, after=_pos_snapshot(pos))
    _grant_lead_role(db, actor, pos)
    db.commit()
    return pos


def _grant_lead_role(db: Session, actor: User, pos: Position) -> None:
    """A new department Lead position gets what the seeded ones have, or its holder could not lead."""
    from app.cli import _grant_once
    from app.permissions.models import Role

    if pos.department_id is None or not pos.is_lead:
        return
    role = db.scalar(select(Role).where(Role.name == "Department Lead"))
    if role is not None:
        _grant_once(db, actor, "position", pos.id, "department", pos.department_id, role=role)
        engine.clear_cache(db)


def update_position(db: Session, actor: User, position_id: int, body: PositionIn) -> Position:
    pos = get_position(db, position_id)
    ensure(db, actor, "org.manage", _scope_for_position(db, pos))
    if body.department_id != pos.department_id:
        ensure(db, actor, "org.manage", department_scope(db, body.department_id))
        if _open_holders(db, [pos.id])[pos.id]:
            raise AppError(409, "POSITION_HELD",
                           "End the current assignments before moving this position to another department.")
    _validate_position_links(db, body, pos.id)
    holders = len(_open_holders(db, [pos.id])[pos.id])
    if body.max_holders < holders:
        raise AppError(409, "POSITION_FULL", f"This position currently has {holders} holder(s).")
    before = _pos_snapshot(pos)
    for key, value in body.model_dump().items():
        setattr(pos, key, value)
    audit.record(db, actor.id, "position.update", "position", pos.id, before=before, after=_pos_snapshot(pos))
    db.commit()
    return pos


def delete_position(db: Session, actor: User, position_id: int, reason: str, confirm_title: str) -> dict:
    """The Chairperson removes a lead, category or other box from the reporting lines, even while
    it is held. Holders lose the position and the access it gave, and whoever reported to it reports
    one level up. The row stays as 'deleted' so people's history still names it."""
    from app.permissions.models import Grant, PermissionAudit

    if not actor.is_super_admin:
        raise forbidden("Only the Chairperson can delete from the reporting lines.")
    pos = get_position(db, position_id)
    if confirm_title.strip().lower() != pos.title.lower():
        raise AppError(422, "CONFIRMATION_MISMATCH", f"Type the position's title, “{pos.title}”, to confirm.")
    holders = _open_holders(db, [pos.id])[pos.id]
    if any(u.is_super_admin for _, u in holders):
        raise AppError(409, "POSITION_PROTECTED", "This is the Chairperson's own position, so it can't be deleted.")
    now, today = utcnow(), _today()
    for pa, _ in holders:
        _close_assignment(db, actor, pa, max(today, pa.valid_from), "removed", f"{pos.title} was deleted")
    grants = db.scalars(select(Grant).where(Grant.revoked_at.is_(None), Grant.subject_type == "position",
                                            Grant.subject_id == pos.id)).all()
    for g in grants:
        g.revoked_at, g.revoked_by = now, actor.id
        db.add(PermissionAudit(actor_id=actor.id, action="revoke", subject_type=g.subject_type,
                               subject_id=g.subject_id, permission_code=g.permission_code, role_id=g.role_id,
                               scope_type=g.scope_type, scope_id=g.scope_id, old_value={"grant_id": g.id},
                               reason=f"Position deleted: {reason}"))
    moved = db.execute(update(Position).where(Position.reports_to_position_id == pos.id, Position.status != "deleted")
                       .values(reports_to_position_id=pos.reports_to_position_id)).rowcount
    summary = {"holders_removed": len(holders), "grants_revoked": len(grants), "reports_moved": moved}
    before = _pos_snapshot(pos)
    pos.status = "deleted"
    audit.record(db, actor.id, "position.delete", "position", pos.id, before=before,
                 after={**_pos_snapshot(pos), "reason": reason, **summary})
    engine.clear_cache(db)
    db.commit()
    return summary


def set_position_status(db: Session, actor: User, position_id: int, archive: bool, reason: str) -> Position:
    pos = get_position(db, position_id)
    ensure(db, actor, "org.manage", _scope_for_position(db, pos))
    if archive and _open_holders(db, [pos.id])[pos.id]:
        raise AppError(409, "POSITION_HELD", "End the current assignments before archiving this position.")
    if not archive and pos.department_id and get_department(db, pos.department_id).status != "active":
        raise AppError(409, "INVALID_STATE", "Restore its department first.")
    before = _pos_snapshot(pos)
    pos.status = "archived" if archive else "active"
    if archive:  # nobody should report to an archived position
        db.execute(update(Position).where(Position.reports_to_position_id == pos.id)
                   .values(reports_to_position_id=pos.reports_to_position_id))
    audit.record(db, actor.id, "position.archive" if archive else "position.restore", "position", pos.id,
                 before=before, after={**_pos_snapshot(pos), "reason": reason})
    db.commit()
    return pos


# ---------------------------------------------------------------- assignments

def _ensure_membership(db: Session, actor: User, user_id: int, department_id: int, start: date) -> None:
    exists = db.scalar(select(DepartmentMembership.id).where(
        DepartmentMembership.user_id == user_id, DepartmentMembership.department_id == department_id,
        DepartmentMembership.valid_to.is_(None)))
    if not exists:
        m = DepartmentMembership(user_id=user_id, department_id=department_id, valid_from=start,
                                 assigned_by=actor.id)
        db.add(m)
        db.flush()
        audit.record(db, actor.id, "department.member_add", "department", department_id,
                     after={"user_id": user_id, "membership_id": m.id, "auto": True})


def _open_assignment(db: Session, actor: User, user: User, pos: Position, start: date,
                     reason: str, note: str | None) -> PositionAssignment:
    if pos.status != "active":
        raise AppError(409, "INVALID_STATE", "This position is archived.")
    if pos.is_category:
        raise AppError(409, "IS_CATEGORY", "This is a category, so nobody can be assigned to it.")
    holders = _open_holders(db, [pos.id])[pos.id]
    if any(u.id == user.id for _, u in holders):
        raise AppError(409, "ALREADY_HOLDS", f"{user.full_name} already holds this position.")
    if len(holders) >= pos.max_holders:
        raise AppError(409, "POSITION_FULL",
                       f"{pos.title} allows {pos.max_holders} holder(s) and is full. End an assignment first.")
    pa = PositionAssignment(user_id=user.id, position_id=pos.id, valid_from=start,
                            start_reason=reason, note=note, assigned_by=actor.id)
    db.add(pa)
    db.flush()
    if pos.department_id:
        _ensure_membership(db, actor, user.id, pos.department_id, start)
    audit.record(db, actor.id, "position.assign", "position", pos.id,
                 after={"user_id": user.id, "assignment_id": pa.id, "valid_from": start.isoformat(),
                        "start_reason": reason, "note": note})
    return pa


def assign(db: Session, actor: User, position_id: int, body: AssignIn) -> PositionAssignment:
    pos = get_position(db, position_id)
    _ensure_can_staff(db, actor, pos)
    user = _active_user(db, body.user_id)
    pa = _open_assignment(db, actor, user, pos, body.valid_from or _today(), body.start_reason, body.note)
    engine.clear_cache(db)
    db.commit()
    return pa


def _get_open_assignment(db: Session, assignment_id: int) -> PositionAssignment:
    pa = db.get(PositionAssignment, assignment_id)
    if pa is None:
        raise not_found("Assignment")
    if pa.valid_to is not None:
        raise AppError(409, "INVALID_STATE", "This assignment has already ended.")
    return pa


def _close_assignment(db: Session, actor: User, pa: PositionAssignment, end: date, reason: str,
                      note: str | None) -> None:
    if end < pa.valid_from:
        raise AppError(422, "VALIDATION_ERROR", "The end date cannot be before the start date.")
    pa.valid_to = end
    pa.end_reason = reason
    pa.ended_by = actor.id
    if note:
        pa.note = f"{pa.note}\n{note}" if pa.note else note
    audit.record(db, actor.id, "position.end", "position", pa.position_id,
                 after={"user_id": pa.user_id, "assignment_id": pa.id, "valid_to": end.isoformat(),
                        "end_reason": reason, "note": note})


def end_assignment(db: Session, actor: User, assignment_id: int, body: EndAssignmentIn) -> PositionAssignment:
    pa = _get_open_assignment(db, assignment_id)
    _ensure_can_staff(db, actor, get_position(db, pa.position_id))
    _close_assignment(db, actor, pa, body.valid_to or _today(), body.end_reason, body.note)
    engine.clear_cache(db)
    db.commit()
    return pa


def transfer(db: Session, actor: User, assignment_id: int, body: TransferIn) -> PositionAssignment:
    """Promotion or transfer: close the current assignment and open the new one together."""
    pa = _get_open_assignment(db, assignment_id)
    old_pos = get_position(db, pa.position_id)
    new_pos = get_position(db, body.to_position_id)
    if new_pos.id == old_pos.id:
        raise AppError(422, "VALIDATION_ERROR", "Choose a different position.")
    _ensure_can_staff(db, actor, old_pos)
    _ensure_can_staff(db, actor, new_pos)
    user = _active_user(db, pa.user_id)
    effective = body.effective or _today()
    _close_assignment(db, actor, pa, effective, body.reason, body.note)
    new_pa = _open_assignment(db, actor, user, new_pos, effective, body.reason, body.note)
    engine.clear_cache(db)
    db.commit()
    return new_pa


# ---------------------------------------------------------------- memberships

def add_member(db: Session, actor: User, dept_id: int, body: MemberIn) -> DepartmentMembership:
    dept = get_department(db, dept_id)
    ensure(db, actor, "org.assign", department_scope(db, dept.id))
    if dept.status != "active":
        raise AppError(409, "INVALID_STATE", "This department is archived.")
    user = _active_user(db, body.user_id)
    if db.scalar(select(DepartmentMembership.id).where(
            DepartmentMembership.user_id == user.id, DepartmentMembership.department_id == dept.id,
            DepartmentMembership.valid_to.is_(None))):
        raise AppError(409, "ALREADY_MEMBER", f"{user.full_name} is already in {dept.name}.")
    m = DepartmentMembership(user_id=user.id, department_id=dept.id,
                             valid_from=body.valid_from or _today(), assigned_by=actor.id)
    db.add(m)
    db.flush()
    audit.record(db, actor.id, "department.member_add", "department", dept.id,
                 after={"user_id": user.id, "membership_id": m.id})
    engine.clear_cache(db)
    db.commit()
    return m


def ensure_can_staff(db: Session, actor: User, pos: Position) -> None:
    _ensure_can_staff(db, actor, pos)


def place_member(db: Session, actor: User, user: User, dept: Department, pos: Position | None) -> None:
    """Put an approved recruit into their department (and position, if one was chosen). The
    proposer's right to do so was checked when they proposed. The caller commits."""
    _ensure_membership(db, actor, user.id, dept.id, _today())
    if pos is not None:
        _open_assignment(db, actor, user, pos, _today(), "appointed", None)
    engine.clear_cache(db)


def end_membership(db: Session, actor: User, membership_id: int, reason: str) -> DepartmentMembership:
    m = db.get(DepartmentMembership, membership_id)
    if m is None:
        raise not_found("Membership")
    if m.valid_to is not None:
        raise AppError(409, "INVALID_STATE", "This membership has already ended.")
    ensure(db, actor, "org.assign", department_scope(db, m.department_id))
    holds = db.scalar(select(func.count()).select_from(PositionAssignment)
                      .join(Position, Position.id == PositionAssignment.position_id)
                      .where(PositionAssignment.user_id == m.user_id, PositionAssignment.valid_to.is_(None),
                             Position.department_id == m.department_id))
    if holds:
        raise AppError(409, "HOLDS_POSITION",
                       "This person holds a position in the department. End that assignment first.")
    m.valid_to = max(_today(), m.valid_from)
    m.end_reason = reason
    m.ended_by = actor.id
    audit.record(db, actor.id, "department.member_remove", "department", m.department_id,
                 after={"user_id": m.user_id, "membership_id": m.id, "reason": reason})
    engine.clear_cache(db)
    db.commit()
    return m


def membership_views(db: Session, rows: list[DepartmentMembership]) -> list[dict]:
    users = {u.id: u for u in db.scalars(select(User).where(User.id.in_({m.user_id for m in rows})))}
    depts = dict(db.execute(select(Department.id, Department.name)
                            .where(Department.id.in_({m.department_id for m in rows}))).all())
    return [{"id": m.id, "user": _person(users[m.user_id]), "department_id": m.department_id,
             "department_name": depts[m.department_id], "valid_from": m.valid_from,
             "valid_to": m.valid_to, "end_reason": m.end_reason} for m in rows]


def assignment_views(db: Session, rows: list[PositionAssignment]) -> list[dict]:
    users = {u.id: u for u in db.scalars(select(User).where(User.id.in_({a.user_id for a in rows})))}
    positions = {p.id: p for p in db.scalars(select(Position).where(Position.id.in_({a.position_id for a in rows})))}
    depts = dict(db.execute(select(Department.id, Department.name).where(Department.id.in_(
        {p.department_id for p in positions.values() if p.department_id}))).all())
    return [{"id": a.id, "user": _person(users[a.user_id]), "position_id": a.position_id,
             "position_title": positions[a.position_id].title,
             "department_id": positions[a.position_id].department_id,
             "department_name": depts.get(positions[a.position_id].department_id),
             "valid_from": a.valid_from, "valid_to": a.valid_to, "start_reason": a.start_reason,
             "end_reason": a.end_reason, "note": a.note} for a in rows]


def department_members(db: Session, dept_id: int) -> list[DepartmentMembership]:
    return list(db.scalars(select(DepartmentMembership).where(
        DepartmentMembership.department_id == dept_id, DepartmentMembership.valid_to.is_(None))
        .order_by(DepartmentMembership.valid_from)))


def position_history(db: Session, position_id: int) -> list[PositionAssignment]:
    return list(db.scalars(select(PositionAssignment).where(PositionAssignment.position_id == position_id)
                           .order_by(PositionAssignment.valid_from.desc(), PositionAssignment.id.desc())))


# ---------------------------------------------------------------- people & profiles

def user_org(db: Session, user_id: int) -> dict:
    user = db.get(User, user_id)
    if user is None:
        raise not_found("User")
    profile = db.get(MemberProfile, user_id)
    positions =db.scalars(select(PositionAssignment).where(PositionAssignment.user_id == user_id)
                           .order_by(PositionAssignment.valid_to.is_(None).desc(),
                                     PositionAssignment.valid_from.desc())).all()
    memberships = db.scalars(select(DepartmentMembership).where(DepartmentMembership.user_id == user_id)
                             .order_by(DepartmentMembership.valid_to.is_(None).desc(),
                                       DepartmentMembership.valid_from.desc())).all()
    return {"user": _person(user), "profile": profile or MemberProfile(lifecycle_status="onboarding"),
            "positions": assignment_views(db, list(positions)),
            "memberships": membership_views(db, list(memberships))}


def profile_complete(db: Session, user: User) -> bool:
    """Team members fill these in after their first sign-in. The IETE membership ID stays optional."""
    if user.user_type != "team":
        return True
    p = db.get(MemberProfile, user.id)
    return bool(p and p.uid and p.official_email and p.block and p.phone and p.branch and p.year_of_study)


def _profile_snapshot(p: MemberProfile) -> dict:
    return {k: (v.isoformat() if isinstance(v, date) else v) for k, v in {
        "uid": p.uid, "iete_membership_id": p.iete_membership_id, "official_email": p.official_email, "block": p.block, "phone": p.phone, "branch": p.branch, "year_of_study": p.year_of_study,
        "joined_on": p.joined_on, "lifecycle_status": p.lifecycle_status,
        "responsibilities": p.responsibilities}.items()}


def update_profile(db: Session, actor: User, user_id: int, body: ProfileIn | SelfProfileIn) -> MemberProfile:
    if db.get(User, user_id) is None:
        raise not_found("User")
    profile = db.get(MemberProfile, user_id)
    if profile is None:
        profile = MemberProfile(user_id=user_id, lifecycle_status="onboarding")
        db.add(profile)
        before = None
    else:
        before = _profile_snapshot(profile)
    for key, value in body.model_dump(exclude_unset=True).items():
        if key == "lifecycle_status" and value is None:
            continue
        if isinstance(value, str):
            value = value.strip() or None
            if key == "block" and value:
                value = value.upper()
        setattr(profile, key, value)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise AppError(409, "UID_TAKEN", "Another member already has this university ID.")
    audit.record(db, actor.id, "profile.update", "user", user_id, before=before,
                 after=_profile_snapshot(profile))
    db.commit()
    return profile


def people(db: Session, q: str | None, limit: int) -> list[User]:
    stmt = select(User).where(User.user_type == "team", User.status.in_(("active", "invited")))
    if q:
        stmt = stmt.where(User.full_name.ilike(f"%{q}%") | User.email.ilike(f"%{q}%"))
    return list(db.scalars(stmt.order_by(User.full_name).limit(limit)))


# ---------------------------------------------------------------- chart

def chart(db: Session, visible: set[int] | None) -> list[dict]:
    stmt = select(Position).where(Position.status == "active")
    if visible is not None:
        stmt = stmt.where(Position.department_id.in_(visible))
    positions = list(db.scalars(stmt.order_by(Position.rank_order, Position.title)))
    views = position_views(db, positions)
    ids = {p.id for p in positions}
    return [{"position_id": v["id"], "title": v["title"], "department_id": v["department_id"],
             "department_name": v["department_name"],
             # A line to a position the viewer cannot see is dropped so the node becomes a root.
             "reports_to_position_id": v["reports_to_position_id"] if v["reports_to_position_id"] in ids else None,
             "is_lead": v["is_lead"], "is_deputy": v["is_deputy"], "is_category": v["is_category"], "max_holders": v["max_holders"],
             "holders": [h["user"] for h in v["holders"]]} for v in views]


# ---------------------------------------------------------------- terms

def save_term(db: Session, actor: User, body: TermIn, term_id: int | None = None) -> Term:
    term = db.get(Term, term_id) if term_id else Term()
    if term is None:
        raise not_found("Term")
    before = None if term_id is None else {"name": term.name, "is_current": term.is_current}
    if body.is_current:
        db.execute(update(Term).where(Term.is_current.is_(True)).values(is_current=False))
    term.name = body.name.strip()
    term.starts_on = body.starts_on
    term.ends_on = body.ends_on
    term.is_current = body.is_current
    if term_id is None:
        db.add(term)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise AppError(409, "NAME_TAKEN", "A term with this name already exists.")
    audit.record(db, actor.id, "term.save", "term", term.id, before=before,
                 after={"name": term.name, "starts_on": term.starts_on.isoformat(),
                        "ends_on": term.ends_on.isoformat(), "is_current": term.is_current})
    db.commit()
    return term
