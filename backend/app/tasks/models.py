"""Tasks. A task belongs to a department, an event, or both; that decides who can see and manage
it. 'Overdue' is never stored: it is due_at in the past while the task is still open."""
from datetime import datetime

from sqlalchemy import (BigInteger, CheckConstraint, DateTime, ForeignKey, Identity, Index, Text,
                        func, text)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

TASK_STATUSES = ("not_started", "assigned", "in_progress", "submitted", "under_review",
                 "completed", "rejected")
TASK_PRIORITIES = ("low", "medium", "high", "urgent")
REVIEW_OUTCOMES = ("accepted", "rejected", "changes_requested")


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        CheckConstraint(f"status IN {TASK_STATUSES}", name="tasks_status_check"),
        CheckConstraint(f"priority IN {TASK_PRIORITIES}", name="tasks_priority_check"),
        CheckConstraint("department_id IS NOT NULL OR event_id IS NOT NULL", name="tasks_has_owner_check"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    priority: Mapped[str] = mapped_column(Text, server_default="medium")
    status: Mapped[str] = mapped_column(Text, server_default="not_started")
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"), index=True)
    event_id: Mapped[int | None] = mapped_column(ForeignKey("events.id"), index=True)
    reviewer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(),
                                                 onupdate=func.now())


class TaskAssignee(Base):
    """Effective-dated: unassigning sets unassigned_at, so who worked on what is never lost."""
    __tablename__ = "task_assignees"
    __table_args__ = (
        Index("task_assignees_one_open", "task_id", "user_id", unique=True,
              postgresql_where=text("unassigned_at IS NULL")),
        Index("task_assignees_open_by_user", "user_id", postgresql_where=text("unassigned_at IS NULL")),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    assigned_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    unassigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TaskDependency(Base):
    __tablename__ = "task_dependencies"
    __table_args__ = (CheckConstraint("task_id <> depends_on_task_id", name="task_dep_not_self"),)

    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), primary_key=True)
    depends_on_task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), primary_key=True)


class TaskComment(Base):
    __tablename__ = "task_comments"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), index=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TaskStatusHistory(Base):
    __tablename__ = "task_status_history"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), index=True)
    from_status: Mapped[str | None] = mapped_column(Text)
    to_status: Mapped[str] = mapped_column(Text)
    changed_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    remarks: Mapped[str | None] = mapped_column(Text)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TaskSubmission(Base):
    """Evidence of work: a note and/or a link. File evidence arrives with Documents (Phase 4)."""
    __tablename__ = "task_submissions"
    __table_args__ = (
        CheckConstraint(f"review_outcome IN {REVIEW_OUTCOMES}", name="task_sub_outcome_check"),
        CheckConstraint("note IS NOT NULL OR link_url IS NOT NULL", name="task_sub_has_evidence"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), index=True)
    submitted_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    note: Mapped[str | None] = mapped_column(Text)
    link_url: Mapped[str | None] = mapped_column(Text)
    review_outcome: Mapped[str | None] = mapped_column(Text)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    review_remarks: Mapped[str | None] = mapped_column(Text)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
