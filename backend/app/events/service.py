"""Events: proposal and approval, and the event workspace (team, milestones, checklist).

Approval chain (decided with the Chairperson, 2026-11-01):
    draft → proposed            the owner submits the proposal
    proposed → awaiting_approval leadership forwards it            (events.review)
    awaiting_approval → approved the Chairperson approves          (events.approve)
then open for registration → ongoing → completed → archived. Reviewers and approvers can send
an event back to draft with a reason. Nobody reviews or approves an event they own
(docs/02-permissions.md §6.4), except the super admin, who has no one above them.

Who can see an event: anyone holding events.view on one of its departments (or everywhere),
plus its owner and its current team.
"""
import re
import secrets
from dataclasses import dataclass

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.audit import service as audit
from app.core.errors import AppError, forbidden, not_found
from app.core.time import utcnow
from app.events.models import (Event, EventChecklistItem, EventDepartment, EventMilestone,
                               EventStatusHistory, EventTeamMember)
from app.events.schemas import ChecklistItemIn, EventIn, MilestoneIn, TeamMemberIn, TransitionIn
from app.notifications.service import notify
from app.org.models import Department, Term
from app.org.service import active_team_user, people_by_id
from app.permissions import engine
from app.permissions.engine import GLOBAL, Scope, can, department_scope, visible_department_ids
from app.tasks.models import Task
from app.users.models import User

CLOSED = ("cancelled", "archived")
STATUS_LABELS = {"draft": "a draft", "proposed": "proposed", "awaiting_approval": "awaiting approval",
                 "approved": "approved", "open_for_registration": "open for registration",
                 "ongoing": "ongoing", "completed": "completed", "cancelled": "cancelled",
                 "archived": "archived"}


@dataclass(frozen=True)
class Transition:
    to: str
    label: str
    rule: str                    # owner_or_edit | review | approve | edit | archive
    needs_remarks: bool = False
    tone: str = "primary"


TRANSITIONS: dict[str, list[Transition]] = {
    "draft": [Transition("proposed", "Submit proposal", "owner_or_edit"),
              Transition("cancelled", "Withdraw", "owner_or_edit", True, "danger")],
    "proposed": [Transition("awaiting_approval", "Forward for approval", "review"),
                 Transition("draft", "Send back for changes", "review", True, "secondary"),
                 Transition("cancelled", "Withdraw", "owner_or_edit", True, "danger")],
    "awaiting_approval": [Transition("approved", "Approve", "approve"),
                          Transition("draft", "Send back for changes", "approve", True, "secondary"),
                          Transition("cancelled", "Reject", "approve", True, "danger")],
    "approved": [Transition("open_for_registration", "Open registration", "edit"),
                 Transition("ongoing", "Start event", "edit", tone="secondary"),
                 Transition("cancelled", "Cancel event", "edit", True, "danger")],
    "open_for_registration": [Transition("ongoing", "Start event", "edit"),
                              Transition("cancelled", "Cancel event", "edit", True, "danger")],
    "ongoing": [Transition("completed", "Mark completed", "edit"),
                Transition("cancelled", "Cancel event", "edit", True, "danger")],
    "completed": [Transition("archived", "Archive", "archive", tone="secondary")],
    "cancelled": [Transition("archived", "Archive", "archive", tone="secondary")],
    "archived": [],
}


# ---------------------------------------------------------------- scope & access

def event_scope(db: Session, event_id: int | None, department_ids=None) -> Scope:
    """An event's scope sits inside each of its departments, so department grants cover it."""
    if department_ids is None:
        department_ids = db.scalars(select(EventDepartment.department_id)
                                    .where(EventDepartment.event_id == event_id)).all()
    return Scope("event", event_id, tuple(department_scope(db, d) for d in department_ids))


def _on_team(db: Session, user_id: int, event_id: int) -> bool:
    return db.scalar(select(EventTeamMember.id).where(
        EventTeamMember.event_id == event_id, EventTeamMember.user_id == user_id,
        EventTeamMember.removed_at.is_(None))) is not None


def can_view(db: Session, user: User, ev: Event, scope: Scope) -> bool:
    return (ev.owner_id == user.id or can(db, user, "events.view", scope)
            or _on_team(db, user.id, ev.id))


def _may(db: Session, user: User, ev: Event, scope: Scope, rule: str) -> bool:
    owner = ev.owner_id == user.id
    if rule == "owner_or_edit":
        return owner or can(db, user, "events.edit", scope)
    if rule in ("review", "approve"):
        perm = "events.review" if rule == "review" else "events.approve"
        return can(db, user, perm, scope) and (not owner or user.is_super_admin)
    return can(db, user, "events.archive" if rule == "archive" else "events.edit", scope)


def can_edit_details(db: Session, user: User, ev: Event, scope: Scope) -> bool:
    """The owner shapes their proposal while it is a draft; after that it needs events.edit."""
    return ev.status not in CLOSED and (
        can(db, user, "events.edit", scope) or (ev.owner_id == user.id and ev.status == "draft"))


def can_manage(db: Session, user: User, ev: Event, scope: Scope) -> bool:
    """Team, milestones and checklist: the owner runs their event, as does anyone with events.edit."""
    return ev.status not in CLOSED and (ev.owner_id == user.id or can(db, user, "events.edit", scope))


def can_add_tasks(db: Session, user: User, ev: Event, scope: Scope) -> bool:
    return ev.status not in CLOSED and (ev.owner_id == user.id or can(db, user, "tasks.create", scope))


def visible_event(db: Session, user: User, event_id: int) -> tuple[Event, Scope]:
    """The event and its scope, or 404 when it does not exist or the user may not see it."""
    ev = db.get(Event, event_id)
    if ev is None:
        raise not_found("Event")
    scope = event_scope(db, ev.id)
    if not can_view(db, user, ev, scope):
        raise not_found("Event")
    return ev, scope


def _require(allowed: bool) -> None:
    if not allowed:
        raise forbidden()


# ---------------------------------------------------------------- create & edit

def _slug(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:50] or "event"
    return f"{base}-{secrets.token_hex(3)}"


def _active_departments(db: Session, ids: list[int]) -> list[int]:
    ids = list(dict.fromkeys(ids))
    if not ids:
        return []
    found = dict(db.execute(select(Department.id, Department.status).where(Department.id.in_(ids))).all())
    for d in ids:
        if d not in found:
            raise not_found("Department")
        if found[d] != "active":
            raise AppError(409, "INVALID_STATE", "One of the chosen departments is archived.")
    return ids


def _check_can_place(db: Session, actor: User, dept_ids: list[int], perms: tuple[str, ...]) -> None:
    """Events belong to departments. Without an organisation-wide grant, a person can only put
    an event in departments where they hold one of `perms`."""
    if not dept_ids:
        if not any(can(db, actor, p, GLOBAL) for p in perms):
            raise AppError(422, "DEPARTMENT_REQUIRED", "Choose the department this event belongs to.")
        return
    for d in dept_ids:
        if not any(can(db, actor, p, department_scope(db, d)) for p in perms):
            raise forbidden("You can only add events to your own department(s).")


def _snapshot(ev: Event, dept_ids) -> dict:
    return {"name": ev.name, "category": ev.category, "venue": ev.venue,
            "starts_at": ev.starts_at.isoformat() if ev.starts_at else None,
            "ends_at": ev.ends_at.isoformat() if ev.ends_at else None,
            "capacity": ev.capacity, "is_public": ev.is_public,
            "budget_planned": str(ev.budget_planned) if ev.budget_planned is not None else None,
            "department_ids": sorted(dept_ids), "status": ev.status}


def _apply(ev: Event, body: EventIn) -> None:
    ev.name = body.name.strip()
    for field in ("category", "description", "venue"):
        value = getattr(body, field)
        setattr(ev, field, (value.strip() or None) if isinstance(value, str) else value)
    ev.starts_at, ev.ends_at = body.starts_at, body.ends_at
    ev.capacity, ev.budget_planned, ev.is_public = body.capacity, body.budget_planned, body.is_public


def create_event(db: Session, actor: User, body: EventIn) -> Event:
    dept_ids = _active_departments(db, body.department_ids)
    _check_can_place(db, actor, dept_ids, ("events.create",))
    ev = Event(slug=_slug(body.name), owner_id=actor.id, created_by=actor.id,
               term_id=db.scalar(select(Term.id).where(Term.is_current.is_(True))))
    _apply(ev, body)
    db.add(ev)
    db.flush()
    db.add_all(EventDepartment(event_id=ev.id, department_id=d) for d in dept_ids)
    db.add(EventStatusHistory(event_id=ev.id, from_status=None, to_status="draft", changed_by=actor.id))
    audit.record(db, actor.id, "event.create", "event", ev.id, after=_snapshot(ev, dept_ids))
    db.commit()
    return ev


def update_event(db: Session, actor: User, event_id: int, body: EventIn) -> Event:
    ev, scope = visible_event(db, actor, event_id)
    _require(can_edit_details(db, actor, ev, scope))
    old_depts = set(db.scalars(select(EventDepartment.department_id).where(EventDepartment.event_id == ev.id)))
    new_depts = _active_departments(db, body.department_ids)
    added = [d for d in new_depts if d not in old_depts]
    if added or not new_depts:
        _check_can_place(db, actor, added, ("events.create", "events.edit"))
    before = _snapshot(ev, old_depts)
    _apply(ev, body)
    if set(new_depts) != old_depts:
        db.execute(delete(EventDepartment).where(EventDepartment.event_id == ev.id))
        db.add_all(EventDepartment(event_id=ev.id, department_id=d) for d in new_depts)
    audit.record(db, actor.id, "event.update", "event", ev.id, before=before, after=_snapshot(ev, new_depts))
    db.commit()
    return ev


# ---------------------------------------------------------------- status

def allowed_transitions(db: Session, user: User, ev: Event, scope: Scope) -> list[Transition]:
    return [t for t in TRANSITIONS[ev.status] if _may(db, user, ev, scope, t.rule)]


def transition(db: Session, actor: User, event_id: int, body: TransitionIn) -> Event:
    ev, scope = visible_event(db, actor, event_id)
    t = next((t for t in TRANSITIONS[ev.status] if t.to == body.to_status), None)
    if t is None:
        raise AppError(409, "INVALID_TRANSITION", f"An event that is {STATUS_LABELS[ev.status]} cannot "
                                                  f"become {STATUS_LABELS.get(body.to_status, body.to_status)}.")
    if not _may(db, actor, ev, scope, t.rule):
        if t.rule in ("review", "approve") and ev.owner_id == actor.id:
            raise forbidden("You cannot review or approve an event you own. Someone else has to.")
        raise forbidden()
    remarks = (body.remarks or "").strip() or None
    if t.needs_remarks and (not remarks or len(remarks) < 3):
        raise AppError(422, "REMARKS_REQUIRED", "Please add a short reason; the owner will see it.")
    if t.to == "proposed" and ev.starts_at is None:
        raise AppError(422, "INCOMPLETE", "Add the event's start date and time before submitting it.")

    previous = ev.status
    ev.status = t.to
    db.add(EventStatusHistory(event_id=ev.id, from_status=previous, to_status=t.to,
                              changed_by=actor.id, remarks=remarks))
    audit.record(db, actor.id, "event.transition", "event", ev.id, before={"status": previous},
                 after={"status": t.to, "remarks": remarks})
    payload = {"event_id": ev.id, "name": ev.name, "from_status": previous, "to_status": t.to,
               "remarks": remarks, "by": actor.full_name}
    notify(db, [ev.owner_id], "event.status", payload, actor.id)
    if t.to == "proposed":
        notify(db, engine.users_who_can(db, "events.review", scope, {ev.owner_id}),
               "event.needs_review", payload, actor.id)
    elif t.to == "awaiting_approval":
        notify(db, engine.users_who_can(db, "events.approve", scope, {ev.owner_id}),
               "event.needs_approval", payload, actor.id)
    db.commit()
    return ev


# ---------------------------------------------------------------- team

def add_team_member(db: Session, actor: User, event_id: int, body: TeamMemberIn) -> None:
    ev, scope = visible_event(db, actor, event_id)
    _require(can_manage(db, actor, ev, scope))
    user = active_team_user(db, body.user_id)
    if _on_team(db, user.id, ev.id):
        raise AppError(409, "ALREADY_ON_TEAM", f"{user.full_name} is already on this event's team.")
    m = EventTeamMember(event_id=ev.id, user_id=user.id, event_role=body.event_role.strip().lower(),
                        added_by=actor.id)
    db.add(m)
    db.flush()
    audit.record(db, actor.id, "event.team_add", "event", ev.id,
                 after={"user_id": user.id, "event_role": m.event_role, "team_member_id": m.id})
    notify(db, [user.id], "event.team_added",
           {"event_id": ev.id, "name": ev.name, "event_role": m.event_role, "by": actor.full_name}, actor.id)
    db.commit()


def remove_team_member(db: Session, actor: User, event_id: int, member_id: int) -> None:
    ev, scope = visible_event(db, actor, event_id)
    _require(can_manage(db, actor, ev, scope))
    m = db.get(EventTeamMember, member_id)
    if m is None or m.event_id != ev.id or m.removed_at is not None:
        raise not_found("Team member")
    m.removed_at, m.removed_by = utcnow(), actor.id
    audit.record(db, actor.id, "event.team_remove", "event", ev.id,
                 after={"user_id": m.user_id, "team_member_id": m.id})
    db.commit()


# ---------------------------------------------------------------- milestones & checklist

def _workspace_item(db: Session, actor: User, event_id: int, model, item_id: int | None):
    ev, scope = visible_event(db, actor, event_id)
    _require(can_manage(db, actor, ev, scope))
    if item_id is None:
        return ev, None
    item = db.get(model, item_id)
    if item is None or item.event_id != ev.id:
        raise not_found("Item")
    return ev, item


def save_milestone(db: Session, actor: User, event_id: int, body: MilestoneIn, item_id: int | None = None) -> None:
    ev, m = _workspace_item(db, actor, event_id, EventMilestone, item_id)
    if m is None:
        m = EventMilestone(event_id=ev.id)
        db.add(m)
    m.title, m.due_at = body.title.strip(), body.due_at
    m.done_at = (m.done_at or utcnow()) if body.done else None
    db.commit()


def save_checklist_item(db: Session, actor: User, event_id: int, body: ChecklistItemIn,
                        item_id: int | None = None) -> None:
    ev, item = _workspace_item(db, actor, event_id, EventChecklistItem, item_id)
    if item is None:
        last = db.scalar(select(func.max(EventChecklistItem.sort_order)).where(EventChecklistItem.event_id == ev.id))
        item = EventChecklistItem(event_id=ev.id, sort_order=(last or 0) + 1)
        db.add(item)
    item.label = body.label.strip()
    if body.done and item.done_at is None:
        item.done_at, item.done_by = utcnow(), actor.id
    elif not body.done:
        item.done_at, item.done_by = None, None
    db.commit()


def delete_workspace_item(db: Session, actor: User, event_id: int, model, item_id: int) -> None:
    _, item = _workspace_item(db, actor, event_id, model, item_id)
    db.delete(item)
    db.commit()


# ---------------------------------------------------------------- lists & views

def list_events(db: Session, user: User, status: str | None, q: str | None, view: str) -> list[Event]:
    stmt = select(Event)
    team_events = select(EventTeamMember.event_id).where(EventTeamMember.user_id == user.id,
                                                         EventTeamMember.removed_at.is_(None))
    if view == "mine":
        stmt = stmt.where(or_(Event.owner_id == user.id, Event.id.in_(team_events)))
    else:
        visible = visible_department_ids(db, user, "events.view")
        if visible is not None:
            conditions = [Event.owner_id == user.id, Event.id.in_(team_events)]
            if visible:
                conditions.append(Event.id.in_(select(EventDepartment.event_id)
                                               .where(EventDepartment.department_id.in_(visible))))
            stmt = stmt.where(or_(*conditions))
    if view == "action":
        stmt = stmt.where(Event.status.in_(("proposed", "awaiting_approval")))
    elif status:
        stmt = stmt.where(Event.status == status)
    elif view != "all":
        stmt = stmt.where(Event.status != "archived")
    if q:
        stmt = stmt.where(Event.name.ilike(f"%{q}%"))
    events = list(db.scalars(stmt.order_by(func.coalesce(Event.starts_at, Event.created_at).desc(), Event.id.desc())))
    if view == "action":   # only those this person can actually move forward
        events = [e for e in events
                  if any(t.rule in ("review", "approve") for t in allowed_transitions(db, user, e, event_scope(db, e.id)))]
    return events


def summaries(db: Session, events: list[Event]) -> list[dict]:
    ids = [e.id for e in events]
    if not ids:
        return []
    depts: dict[int, list[dict]] = {i: [] for i in ids}
    for event_id, dept_id, name in db.execute(
            select(EventDepartment.event_id, Department.id, Department.name)
            .join(Department, Department.id == EventDepartment.department_id)
            .where(EventDepartment.event_id.in_(ids)).order_by(Department.name)):
        depts[event_id].append({"id": dept_id, "name": name})
    team = dict(db.execute(select(EventTeamMember.event_id, func.count()).where(
        EventTeamMember.event_id.in_(ids), EventTeamMember.removed_at.is_(None))
        .group_by(EventTeamMember.event_id)).all())
    tasks = dict(db.execute(select(Task.event_id, func.count()).where(
        Task.event_id.in_(ids), Task.status.not_in(("completed", "rejected")))
        .group_by(Task.event_id)).all())
    owners = people_by_id(db, [e.owner_id for e in events])
    return [{"id": e.id, "name": e.name, "slug": e.slug, "category": e.category, "status": e.status,
             "venue": e.venue, "starts_at": e.starts_at, "ends_at": e.ends_at, "owner": owners[e.owner_id],
             "departments": depts[e.id], "team_size": team.get(e.id, 0), "open_tasks": tasks.get(e.id, 0),
             "created_at": e.created_at} for e in events]


def detail(db: Session, user: User, event_id: int) -> dict:
    ev, scope = visible_event(db, user, event_id)
    team = db.scalars(select(EventTeamMember).where(EventTeamMember.event_id == ev.id,
                                                    EventTeamMember.removed_at.is_(None))
                      .order_by(EventTeamMember.added_at)).all()
    milestones = db.scalars(select(EventMilestone).where(EventMilestone.event_id == ev.id)
                            .order_by(EventMilestone.due_at.asc().nulls_last(), EventMilestone.id)).all()
    checklist = db.scalars(select(EventChecklistItem).where(EventChecklistItem.event_id == ev.id)
                           .order_by(EventChecklistItem.sort_order, EventChecklistItem.id)).all()
    # Newest first by insertion order: changed_at is the transaction's start time, so two quick
    # changes can share or invert timestamps, but ids never do.
    history = db.scalars(select(EventStatusHistory).where(EventStatusHistory.event_id == ev.id)
                         .order_by(EventStatusHistory.id.desc())).all()
    people = people_by_id(db, [m.user_id for m in team] + [c.done_by for c in checklist]
                          + [h.changed_by for h in history])
    return {
        **summaries(db, [ev])[0],
        "description": ev.description, "capacity": ev.capacity, "budget_planned": ev.budget_planned,
        "is_public": ev.is_public,
        "team": [{"id": m.id, "user": people[m.user_id], "event_role": m.event_role, "added_at": m.added_at}
                 for m in team],
        "milestones": [{"id": m.id, "title": m.title, "due_at": m.due_at, "done_at": m.done_at} for m in milestones],
        "checklist": [{"id": c.id, "label": c.label, "sort_order": c.sort_order, "done_at": c.done_at,
                       "done_by": people.get(c.done_by)} for c in checklist],
        "history": [{"from_status": h.from_status, "to_status": h.to_status, "changed_by": people[h.changed_by],
                     "remarks": h.remarks, "changed_at": h.changed_at} for h in history],
        "allowed_transitions": [{"to_status": t.to, "label": t.label, "needs_remarks": t.needs_remarks,
                                 "tone": t.tone} for t in allowed_transitions(db, user, ev, scope)],
        "can_edit": can_edit_details(db, user, ev, scope),
        "can_manage": can_manage(db, user, ev, scope),
        "can_add_tasks": can_add_tasks(db, user, ev, scope),
    }
