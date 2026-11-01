"""Events and their workspace. Status changes go through the state machine in service.py and
are written to event_status_history, which is append-only (trigger-protected)."""
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Identity, Index,
                        Integer, Numeric, SmallInteger, Text, func, text)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

EVENT_STATUSES = ("draft", "proposed", "awaiting_approval", "approved", "open_for_registration",
                  "ongoing", "completed", "cancelled", "archived")


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        CheckConstraint(f"status IN {EVENT_STATUSES}", name="events_status_check"),
        CheckConstraint("capacity IS NULL OR capacity > 0", name="events_capacity_check"),
        CheckConstraint("ends_at IS NULL OR starts_at IS NULL OR ends_at >= starts_at", name="events_dates_check"),
        Index("events_status_idx", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    slug: Mapped[str] = mapped_column(Text, unique=True)
    category: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    venue: Mapped[str | None] = mapped_column(Text)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reg_opens_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reg_closes_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    capacity: Mapped[int | None] = mapped_column(Integer)
    allow_teams: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    team_size_min: Mapped[int | None] = mapped_column(SmallInteger)
    team_size_max: Mapped[int | None] = mapped_column(SmallInteger)
    eligibility: Mapped[str | None] = mapped_column(Text)
    is_public: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    status: Mapped[str] = mapped_column(Text, server_default="draft")
    budget_planned: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    term_id: Mapped[int | None] = mapped_column(ForeignKey("terms.id"))
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EventDepartment(Base):
    __tablename__ = "event_departments"

    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), primary_key=True)
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.id"), primary_key=True)


class EventTeamMember(Base):
    """Effective-dated: removing someone sets removed_at, so the event keeps its staffing history."""
    __tablename__ = "event_team"
    __table_args__ = (
        Index("event_team_one_active", "event_id", "user_id", unique=True,
              postgresql_where=text("removed_at IS NULL")),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    event_role: Mapped[str] = mapped_column(Text)            # 'coordinator', 'volunteer', ...
    added_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    removed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


class EventMilestone(Base):
    __tablename__ = "event_milestones"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), index=True)
    title: Mapped[str] = mapped_column(Text)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EventChecklistItem(Base):
    __tablename__ = "event_checklist_items"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), index=True)
    label: Mapped[str] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    done_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EventStatusHistory(Base):
    __tablename__ = "event_status_history"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), index=True)
    from_status: Mapped[str | None] = mapped_column(Text)
    to_status: Mapped[str] = mapped_column(Text)
    changed_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    remarks: Mapped[str | None] = mapped_column(Text)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
