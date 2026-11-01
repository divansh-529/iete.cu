"""Organisation structure. Assignments and memberships are effective-dated: a change closes
the current row (valid_to) and opens a new one, so history is never lost."""
from datetime import date, datetime

from sqlalchemy import (BigInteger, Boolean, CheckConstraint, Date, DateTime, ForeignKey, Identity,
                        Index, Integer, SmallInteger, Text, func, text)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

ORG_STATUSES = ("active", "archived")
# 'deleted': removed by the Chairperson. Hidden everywhere and cannot be restored, but the row
# stays so that past memberships, events and the audit log still show which department it was.
DEPARTMENT_STATUSES = ("active", "archived", "deleted")
START_REASONS = ("appointed", "promoted", "transferred", "reinstated")
END_REASONS = ("promoted", "transferred", "resigned", "removed", "term_ended")
LIFECYCLE_STATUSES = ("onboarding", "probation", "active", "alumni", "removed")


class Term(Base):
    __tablename__ = "terms"
    __table_args__ = (
        CheckConstraint("ends_on > starts_on", name="terms_dates_check"),
        Index("one_current_term", text("(true)"), unique=True, postgresql_where=text("is_current")),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    name: Mapped[str] = mapped_column(Text, unique=True)
    starts_on: Mapped[date] = mapped_column(Date)
    ends_on: Mapped[date] = mapped_column(Date)
    is_current: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))


class Department(Base):
    __tablename__ = "departments"
    __table_args__ = (
        CheckConstraint(f"status IN {DEPARTMENT_STATUSES}", name="departments_status_check"),
        # A deleted department's name can be used again.
        Index("departments_name_unique", text("lower(name)"), unique=True,
              postgresql_where=text("status <> 'deleted'")),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"))
    status: Mapped[str] = mapped_column(Text, server_default="active")
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Position(Base):
    __tablename__ = "positions"
    __table_args__ = (
        CheckConstraint(f"status IN {ORG_STATUSES}", name="positions_status_check"),
        CheckConstraint("max_holders > 0", name="positions_max_holders_check"),
        CheckConstraint("reports_to_position_id IS DISTINCT FROM id", name="positions_not_self_report"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"))  # null = leadership
    reports_to_position_id: Mapped[int | None] = mapped_column(ForeignKey("positions.id"))
    is_lead: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    is_deputy: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    max_holders: Mapped[int] = mapped_column(Integer, server_default=text("1"))
    rank_order: Mapped[int] = mapped_column(Integer, server_default=text("100"))
    status: Mapped[str] = mapped_column(Text, server_default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PositionAssignment(Base):
    __tablename__ = "position_assignments"
    __table_args__ = (
        CheckConstraint(f"start_reason IN {START_REASONS}", name="pa_start_reason_check"),
        CheckConstraint(f"end_reason IN {END_REASONS}", name="pa_end_reason_check"),
        CheckConstraint("valid_to IS NULL OR valid_to >= valid_from", name="pa_dates_check"),
        CheckConstraint("(valid_to IS NULL) = (end_reason IS NULL)", name="pa_end_pair_check"),
        Index("pa_open_by_user", "user_id", postgresql_where=text("valid_to IS NULL")),
        Index("pa_open_by_position", "position_id", postgresql_where=text("valid_to IS NULL")),
        Index("pa_one_open_per_user_position", "user_id", "position_id", unique=True,
              postgresql_where=text("valid_to IS NULL")),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    position_id: Mapped[int] = mapped_column(ForeignKey("positions.id"))
    valid_from: Mapped[date] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    start_reason: Mapped[str] = mapped_column(Text)
    end_reason: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
    assigned_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    ended_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DepartmentMembership(Base):
    __tablename__ = "department_memberships"
    __table_args__ = (
        CheckConstraint("valid_to IS NULL OR valid_to >= valid_from", name="dm_dates_check"),
        Index("dm_one_open_membership", "user_id", "department_id", unique=True,
              postgresql_where=text("valid_to IS NULL")),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.id"))
    valid_from: Mapped[date] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    end_reason: Mapped[str | None] = mapped_column(Text)
    assigned_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    ended_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MemberProfile(Base):
    __tablename__ = "member_profiles"
    __table_args__ = (
        CheckConstraint(f"lifecycle_status IN {LIFECYCLE_STATUSES}", name="mp_lifecycle_check"),
        CheckConstraint("year_of_study BETWEEN 1 AND 6", name="mp_year_check"),
    )

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    uid: Mapped[str | None] = mapped_column(Text, unique=True)        # university ID
    phone: Mapped[str | None] = mapped_column(Text)
    branch: Mapped[str | None] = mapped_column(Text)
    year_of_study: Mapped[int | None] = mapped_column(SmallInteger)
    joined_on: Mapped[date | None] = mapped_column(Date)
    lifecycle_status: Mapped[str] = mapped_column(Text, server_default="onboarding")
    responsibilities: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(),
                                                 onupdate=func.now())
