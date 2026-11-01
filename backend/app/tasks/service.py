"""Tasks: create, assign, work, submit evidence, review.

Status flow:
    not_started → assigned        when someone is assigned
    assigned → in_progress        an assignee starts
    assigned / in_progress → submitted   an assignee submits evidence (note and/or link)
    submitted → completed | in_progress | rejected   the reviewer accepts, asks for changes, rejects
    completed / rejected → assigned      reopened by someone who manages the task
A task cannot be started or submitted while a task it depends on is not completed.

Who can do what. A task's scope sits inside its department and its event, so department grants
cover both. Managing (edit, assign, reopen) needs tasks.create / tasks.assign there, or being the
event's owner. Reviewing needs to be the named reviewer with tasks.review (or the event's owner),
and nobody reviews their own submission. Assignees, the reviewer, the creator and the event's
owner always see the task.
"""
from datetime import datetime

from sqlalchemy import case, delete, or_, select
from sqlalchemy.orm import Session

from app.audit import service as audit
from app.core.errors import AppError, forbidden, not_found
from app.core.time import utcnow
from app.events.models import Event, EventDepartment
from app.events.service import CLOSED as EVENT_CLOSED
from app.events.service import event_scope, visible_event
from app.notifications.service import notify
from app.org.models import Department
from app.org.service import active_team_user, department_names, people_by_id
from app.permissions.engine import Scope, can, department_scope, visible_department_ids
from app.tasks.models import (Task, TaskAssignee, TaskComment, TaskDependency, TaskStatusHistory,
                              TaskSubmission)
from app.tasks.schemas import (AssigneesIn, CommentIn, ReopenIn, ReviewIn, SubmissionIn, TaskCreateIn,
                               TaskIn)
from app.users.models import User

OPEN = ("not_started", "assigned", "in_progress", "submitted", "under_review")
DONE = ("completed", "rejected")
REVIEW_RESULT = {"accepted": "completed", "changes_requested": "in_progress", "rejected": "rejected"}


# ---------------------------------------------------------------- scope & access

def task_scope(db: Session, task_id: int | None, department_id: int | None, event_id: int | None) -> Scope:
    parents = []
    if department_id:
        parents.append(department_scope(db, department_id))
    if event_id:
        parents.append(event_scope(db, event_id))
    return Scope("task", task_id, tuple(parents))


class _Ctx:
    """Everything the access rules need about one task, loaded once."""

    def __init__(self, db: Session, task: Task):
        self.task = task
        self.scope = task_scope(db, task.id, task.department_id, task.event_id)
        self.event = db.get(Event, task.event_id) if task.event_id else None
        self.assignees = set(db.scalars(select(TaskAssignee.user_id).where(
            TaskAssignee.task_id == task.id, TaskAssignee.unassigned_at.is_(None))))
        self.pending = db.scalar(select(TaskSubmission).where(
            TaskSubmission.task_id == task.id, TaskSubmission.review_outcome.is_(None))
            .order_by(TaskSubmission.id.desc()).limit(1))
        self.blocked = db.scalar(select(TaskDependency.depends_on_task_id)
                                 .join(Task, Task.id == TaskDependency.depends_on_task_id)
                                 .where(TaskDependency.task_id == task.id, Task.status != "completed")
                                 .limit(1)) is not None

    def runs_event(self, user: User) -> bool:
        return self.event is not None and self.event.owner_id == user.id and self.event.status not in EVENT_CLOSED


def _manages(db: Session, user: User, scope: Scope, event: Event | None, permission: str) -> bool:
    return can(db, user, permission, scope) or (
        event is not None and event.owner_id == user.id and event.status not in EVENT_CLOSED)


def _involved(user: User, c: _Ctx) -> bool:
    t = c.task
    return user.id in c.assignees or user.id in (t.reviewer_id, t.created_by) or (
        c.event is not None and c.event.owner_id == user.id)


def _can_review(db: Session, user: User, c: _Ctx) -> bool:
    t = c.task
    designated = t.reviewer_id == user.id or (t.reviewer_id is None and can(db, user, "tasks.review", c.scope))
    authority = user.is_super_admin or can(db, user, "tasks.review", c.scope) or c.runs_event(user)
    own_work = c.pending is not None and c.pending.submitted_by == user.id and not user.is_super_admin
    return designated and authority and not own_work


def actions(db: Session, user: User, c: _Ctx) -> list[str]:
    t, result = c.task, ["comment"]
    open_ = t.status not in DONE
    if open_ and (t.created_by == user.id or _manages(db, user, c.scope, c.event, "tasks.create")):
        result.append("edit")
    if open_ and _manages(db, user, c.scope, c.event, "tasks.assign"):
        result.append("assign")
    if user.id in c.assignees and not c.blocked:
        if t.status == "assigned":
            result.append("start")
        if t.status in ("assigned", "in_progress"):
            result.append("submit")
    if t.status in ("submitted", "under_review") and c.pending is not None and _can_review(db, user, c):
        result.append("review")
    if not open_ and _manages(db, user, c.scope, c.event, "tasks.create"):
        result.append("reopen")
    return result


def _visible(db: Session, user: User, task_id: int) -> _Ctx:
    task = db.get(Task, task_id)
    if task is None:
        raise not_found("Task")
    c = _Ctx(db, task)
    if not (_involved(user, c) or can(db, user, "tasks.view", c.scope)):
        raise not_found("Task")
    return c


def _allowed(db: Session, user: User, c: _Ctx, action: str) -> None:
    if action not in actions(db, user, c):
        if action in ("start", "submit") and user.id in c.assignees and c.blocked:
            raise AppError(409, "BLOCKED", "This task is waiting on another task that is not completed yet.")
        if action == "review" and c.pending is not None and c.pending.submitted_by == user.id:
            raise forbidden("You cannot review your own submission. Ask the task's creator to change the reviewer.")
        raise forbidden()


# ---------------------------------------------------------------- helpers

def _set_status(db: Session, actor: User, task: Task, to: str, remarks: str | None = None) -> None:
    if task.status != to:
        db.add(TaskStatusHistory(task_id=task.id, from_status=task.status, to_status=to,
                                 changed_by=actor.id, remarks=remarks))
        task.status = to


def _payload(task: Task, actor: User, **extra) -> dict:
    return {"task_id": task.id, "title": task.title, "by": actor.full_name, **extra}


def _check_home(db: Session, actor: User, body: TaskIn) -> Event | None:
    """Validate the department and event a task belongs to; returns the event (if any)."""
    event = None
    if body.event_id is not None:
        event, _ = visible_event(db, actor, body.event_id)
        if event.status in EVENT_CLOSED:
            raise AppError(409, "INVALID_STATE", "Tasks cannot be added to a cancelled or archived event.")
    if body.department_id is not None:
        dept = db.get(Department, body.department_id)
        if dept is None:
            raise not_found("Department")
        if dept.status != "active":
            raise AppError(409, "INVALID_STATE", "That department is archived.")
    return event


def _set_dependencies(db: Session, task: Task, ids: list[int]) -> None:
    ids = list(dict.fromkeys(ids))
    if task.id in ids:
        raise AppError(422, "VALIDATION_ERROR", "A task cannot depend on itself.")
    found = set(db.scalars(select(Task.id).where(Task.id.in_(ids)))) if ids else set()
    if len(found) != len(ids):
        raise not_found("Task")
    # Following the chain from each new dependency must never lead back to this task.
    stack, seen = list(ids), set()
    while stack:
        current = stack.pop()
        if current == task.id:
            raise AppError(422, "CYCLE", "These dependencies would make tasks wait on each other forever.")
        if current not in seen:
            seen.add(current)
            stack.extend(db.scalars(select(TaskDependency.depends_on_task_id)
                                    .where(TaskDependency.task_id == current, TaskDependency.task_id != task.id)))
    db.execute(delete(TaskDependency).where(TaskDependency.task_id == task.id))
    db.add_all(TaskDependency(task_id=task.id, depends_on_task_id=d) for d in ids)


def _set_assignees(db: Session, actor: User, task: Task, user_ids: list[int]) -> None:
    wanted = list(dict.fromkeys(user_ids))
    for uid in wanted:
        active_team_user(db, uid)
    current = {a.user_id: a for a in db.scalars(select(TaskAssignee).where(
        TaskAssignee.task_id == task.id, TaskAssignee.unassigned_at.is_(None)))}
    now = utcnow()
    for uid, row in current.items():
        if uid not in wanted:
            row.unassigned_at = now
    added = [uid for uid in wanted if uid not in current]
    db.add_all(TaskAssignee(task_id=task.id, user_id=uid, assigned_by=actor.id) for uid in added)
    if wanted and task.status == "not_started":
        _set_status(db, actor, task, "assigned")
    elif not wanted and task.status == "assigned":
        _set_status(db, actor, task, "not_started")
    notify(db, added, "task.assigned", _payload(task, actor, due_at=task.due_at.isoformat() if task.due_at else None),
           actor.id)
    if added or len(wanted) != len(current):
        audit.record(db, actor.id, "task.assign", "task", task.id,
                     before={"assignees": sorted(current)}, after={"assignees": sorted(wanted)})


def _apply(task: Task, body: TaskIn) -> None:
    task.title = body.title.strip()
    task.description = (body.description or "").strip() or None
    task.priority, task.due_at = body.priority, body.due_at
    task.department_id, task.event_id = body.department_id, body.event_id


def _snapshot(t: Task) -> dict:
    return {"title": t.title, "priority": t.priority, "status": t.status,
            "due_at": t.due_at.isoformat() if t.due_at else None, "department_id": t.department_id,
            "event_id": t.event_id, "reviewer_id": t.reviewer_id}


# ---------------------------------------------------------------- create & edit

def create_task(db: Session, actor: User, body: TaskCreateIn) -> Task:
    event = _check_home(db, actor, body)
    scope = task_scope(db, None, body.department_id, body.event_id)
    if not _manages(db, actor, scope, event, "tasks.create"):
        raise forbidden("You can only create tasks for your own department, or for an event you run.")
    if body.assignee_ids and not _manages(db, actor, scope, event, "tasks.assign"):
        raise forbidden("You can create this task but not assign it. Leave the assignees empty.")
    reviewer = active_team_user(db, body.reviewer_id or actor.id)
    task = Task(created_by=actor.id, reviewer_id=reviewer.id)
    _apply(task, body)
    db.add(task)
    db.flush()
    db.add(TaskStatusHistory(task_id=task.id, from_status=None, to_status="not_started", changed_by=actor.id))
    _set_dependencies(db, task, body.depends_on)
    if body.assignee_ids:
        _set_assignees(db, actor, task, body.assignee_ids)
    audit.record(db, actor.id, "task.create", "task", task.id, after=_snapshot(task))
    db.commit()
    return task


def update_task(db: Session, actor: User, task_id: int, body: TaskIn) -> None:
    c = _visible(db, actor, task_id)
    _allowed(db, actor, c, "edit")
    task = c.task
    if (body.department_id, body.event_id) != (task.department_id, task.event_id):
        event = _check_home(db, actor, body)
        if not _manages(db, actor, task_scope(db, task.id, body.department_id, body.event_id), event, "tasks.create"):
            raise forbidden("You can only move tasks to your own department, or to an event you run.")
    before = _snapshot(task)
    _apply(task, body)
    if body.reviewer_id and body.reviewer_id != task.reviewer_id:
        task.reviewer_id = active_team_user(db, body.reviewer_id).id
    _set_dependencies(db, task, body.depends_on)
    audit.record(db, actor.id, "task.update", "task", task.id, before=before, after=_snapshot(task))
    db.commit()


def set_assignees(db: Session, actor: User, task_id: int, body: AssigneesIn) -> None:
    c = _visible(db, actor, task_id)
    _allowed(db, actor, c, "assign")
    _set_assignees(db, actor, c.task, body.user_ids)
    db.commit()


# ---------------------------------------------------------------- work & review

def start(db: Session, actor: User, task_id: int) -> None:
    c = _visible(db, actor, task_id)
    _allowed(db, actor, c, "start")
    _set_status(db, actor, c.task, "in_progress")
    db.commit()


def submit(db: Session, actor: User, task_id: int, body: SubmissionIn) -> None:
    c = _visible(db, actor, task_id)
    _allowed(db, actor, c, "submit")
    task = c.task
    db.add(TaskSubmission(task_id=task.id, submitted_by=actor.id, note=body.note, link_url=body.link_url))
    _set_status(db, actor, task, "submitted")
    audit.record(db, actor.id, "task.submit", "task", task.id, after={"link_url": body.link_url})
    notify(db, [task.reviewer_id], "task.submitted", _payload(task, actor), actor.id)
    db.commit()


def review(db: Session, actor: User, task_id: int, body: ReviewIn) -> None:
    c = _visible(db, actor, task_id)
    _allowed(db, actor, c, "review")
    remarks = (body.remarks or "").strip() or None
    if body.outcome != "accepted" and not remarks:
        raise AppError(422, "REMARKS_REQUIRED", "Tell the assignee what needs to change.")
    sub, task = c.pending, c.task
    sub.review_outcome, sub.reviewed_by, sub.review_remarks, sub.reviewed_at = (
        body.outcome, actor.id, remarks, utcnow())
    _set_status(db, actor, task, REVIEW_RESULT[body.outcome], remarks)
    audit.record(db, actor.id, "task.review", "task", task.id,
                 after={"submission_id": sub.id, "outcome": body.outcome, "remarks": remarks})
    notify(db, {sub.submitted_by, *c.assignees}, "task.reviewed",
           _payload(task, actor, outcome=body.outcome, remarks=remarks), actor.id)
    db.commit()


def reopen(db: Session, actor: User, task_id: int, body: ReopenIn) -> None:
    c = _visible(db, actor, task_id)
    _allowed(db, actor, c, "reopen")
    _set_status(db, actor, c.task, "assigned" if c.assignees else "not_started", body.remarks.strip())
    audit.record(db, actor.id, "task.reopen", "task", c.task.id, after={"remarks": body.remarks.strip()})
    notify(db, c.assignees, "task.reopened", _payload(c.task, actor, remarks=body.remarks.strip()), actor.id)
    db.commit()


def add_comment(db: Session, actor: User, task_id: int, body: CommentIn) -> None:
    c = _visible(db, actor, task_id)
    text = body.body.strip()
    if not text:
        raise AppError(422, "VALIDATION_ERROR", "Write a comment first.")
    db.add(TaskComment(task_id=c.task.id, author_id=actor.id, body=text))
    notify(db, {*c.assignees, c.task.reviewer_id, c.task.created_by}, "task.comment",
           _payload(c.task, actor, excerpt=text[:140]), actor.id)
    db.commit()


# ---------------------------------------------------------------- lists & views

def list_tasks(db: Session, user: User, view: str, department_id: int | None, event_id: int | None,
               status: str | None, q: str | None) -> list[Task]:
    mine = select(TaskAssignee.task_id).where(TaskAssignee.user_id == user.id, TaskAssignee.unassigned_at.is_(None))
    stmt = select(Task)
    if view == "mine":
        stmt = stmt.where(Task.id.in_(mine))
    elif view == "review":
        stmt = stmt.where(Task.reviewer_id == user.id, Task.status.in_(("submitted", "under_review")))
    else:
        visible = visible_department_ids(db, user, "tasks.view")
        if visible is not None:
            conditions = [Task.id.in_(mine), Task.reviewer_id == user.id, Task.created_by == user.id,
                          Task.event_id.in_(select(Event.id).where(Event.owner_id == user.id))]
            if visible:
                conditions += [Task.department_id.in_(visible),
                               Task.event_id.in_(select(EventDepartment.event_id)
                                                 .where(EventDepartment.department_id.in_(visible)))]
            stmt = stmt.where(or_(*conditions))
    if department_id is not None:
        stmt = stmt.where(Task.department_id == department_id)
    if event_id is not None:
        stmt = stmt.where(Task.event_id == event_id)
    if status == "open":
        stmt = stmt.where(Task.status.in_(OPEN))
    elif status == "overdue":
        stmt = stmt.where(Task.status.in_(OPEN), Task.due_at < utcnow())
    elif status:
        stmt = stmt.where(Task.status == status)
    if q:
        stmt = stmt.where(Task.title.ilike(f"%{q}%"))
    finished_last = case((Task.status.in_(DONE), 1), else_=0)
    return list(db.scalars(stmt.order_by(finished_last, Task.due_at.asc().nulls_last(), Task.id.desc()).limit(500)))


def _overdue(t: Task, now: datetime) -> bool:
    return t.due_at is not None and t.due_at < now and t.status in OPEN


def summaries(db: Session, tasks: list[Task]) -> list[dict]:
    ids = [t.id for t in tasks]
    if not ids:
        return []
    assignees: dict[int, list[int]] = {i: [] for i in ids}
    for task_id, user_id in db.execute(select(TaskAssignee.task_id, TaskAssignee.user_id).where(
            TaskAssignee.task_id.in_(ids), TaskAssignee.unassigned_at.is_(None)).order_by(TaskAssignee.assigned_at)):
        assignees[task_id].append(user_id)
    people = people_by_id(db, [u for us in assignees.values() for u in us] + [t.reviewer_id for t in tasks])
    depts = department_names(db, [t.department_id for t in tasks])
    events = dict(db.execute(select(Event.id, Event.name).where(
        Event.id.in_({t.event_id for t in tasks if t.event_id}))).all()) if any(t.event_id for t in tasks) else {}
    now = utcnow()
    return [{"id": t.id, "title": t.title, "priority": t.priority, "status": t.status, "due_at": t.due_at,
             "overdue": _overdue(t, now),
             "department": {"id": t.department_id, "name": depts[t.department_id]} if t.department_id else None,
             "event": {"id": t.event_id, "name": events[t.event_id]} if t.event_id else None,
             "assignees": [people[u] for u in assignees[t.id]], "reviewer": people.get(t.reviewer_id),
             "created_at": t.created_at, "updated_at": t.updated_at} for t in tasks]


def detail(db: Session, user: User, task_id: int) -> dict:
    c = _visible(db, user, task_id)
    t = c.task
    deps = db.execute(select(Task.id, Task.title, Task.status)
                      .join(TaskDependency, TaskDependency.depends_on_task_id == Task.id)
                      .where(TaskDependency.task_id == t.id).order_by(Task.id)).all()
    subs = db.scalars(select(TaskSubmission).where(TaskSubmission.task_id == t.id)
                      .order_by(TaskSubmission.id.desc())).all()
    comments = db.scalars(select(TaskComment).where(TaskComment.task_id == t.id).order_by(TaskComment.id)).all()
    history = db.scalars(select(TaskStatusHistory).where(TaskStatusHistory.task_id == t.id)
                         .order_by(TaskStatusHistory.id.desc())).all()    # insertion order, as for events
    people = people_by_id(db, [t.created_by] + [s.submitted_by for s in subs] + [s.reviewed_by for s in subs]
                          + [m.author_id for m in comments] + [h.changed_by for h in history])
    return {
        **summaries(db, [t])[0],
        "description": t.description, "created_by": people[t.created_by],
        "depends_on": [{"id": i, "title": title, "status": status} for i, title, status in deps],
        "blocked": c.blocked,
        "submissions": [{"id": s.id, "submitted_by": people[s.submitted_by], "note": s.note, "link_url": s.link_url,
                         "submitted_at": s.submitted_at, "review_outcome": s.review_outcome,
                         "reviewed_by": people.get(s.reviewed_by), "review_remarks": s.review_remarks,
                         "reviewed_at": s.reviewed_at} for s in subs],
        "comments": [{"id": m.id, "author": people[m.author_id], "body": m.body, "created_at": m.created_at}
                     for m in comments],
        "history": [{"from_status": h.from_status, "to_status": h.to_status, "changed_by": people[h.changed_by],
                     "remarks": h.remarks, "changed_at": h.changed_at} for h in history],
        "actions": actions(db, user, c),
    }
