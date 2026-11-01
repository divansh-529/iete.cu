"""Create and read in-app notifications.

There is no background scheduler on the free hosting plan, so "task due soon" reminders are
created when the person next checks their notifications (at most one per task).
"""
from datetime import timedelta

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.time import utcnow
from app.notifications.models import Notification

DUE_SOON = timedelta(hours=24)
OPEN_TASK_STATUSES = ("not_started", "assigned", "in_progress")


def notify(db: Session, user_ids, kind: str, payload: dict, actor_id: int | None = None) -> None:
    """Queue a notification for each user (never for the person who caused it). The caller commits."""
    for uid in {u for u in user_ids if u and u != actor_id}:
        db.add(Notification(user_id=uid, kind=kind, payload=payload))


def _add_due_soon(db: Session, user_id: int) -> None:
    from app.tasks.models import Task, TaskAssignee

    now = utcnow()
    due = db.execute(select(Task.id, Task.title, Task.due_at)
                     .join(TaskAssignee, TaskAssignee.task_id == Task.id)
                     .where(TaskAssignee.user_id == user_id, TaskAssignee.unassigned_at.is_(None),
                            Task.status.in_(OPEN_TASK_STATUSES), Task.due_at.is_not(None),
                            Task.due_at > now, Task.due_at <= now + DUE_SOON)).all()
    if not due:
        return
    already = set(db.scalars(select(Notification.payload["task_id"].as_integer()).where(
        Notification.user_id == user_id, Notification.kind == "task.due_soon")))
    for task_id, title, due_at in due:
        if task_id not in already:
            db.add(Notification(user_id=user_id, kind="task.due_soon",
                                payload={"task_id": task_id, "title": title, "due_at": due_at.isoformat()}))
    db.commit()


def list_for(db: Session, user_id: int, limit: int) -> tuple[list[Notification], int]:
    _add_due_soon(db, user_id)
    items = db.scalars(select(Notification).where(Notification.user_id == user_id)
                       .order_by(Notification.created_at.desc(), Notification.id.desc()).limit(limit)).all()
    unread = db.scalar(select(func.count()).select_from(Notification).where(
        Notification.user_id == user_id, Notification.read_at.is_(None)))
    return list(items), unread or 0


def mark_read(db: Session, user_id: int, ids: list[int] | None) -> None:
    stmt = update(Notification).where(Notification.user_id == user_id, Notification.read_at.is_(None))
    if ids is not None:
        stmt = stmt.where(Notification.id.in_(ids))
    db.execute(stmt.values(read_at=utcnow()))
    db.commit()
