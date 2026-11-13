"""Document tracker: paper documents carried from office to office for signatures. See service.py."""
from datetime import date, datetime

from sqlalchemy import (BigInteger, CheckConstraint, Date, DateTime, ForeignKey, Identity, Integer, Text,
                        UniqueConstraint, func)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

TRACKER_STATUSES = ("in_progress", "completed", "rejected", "cancelled")
STEP_STATUSES = ("pending", "submitted", "returned", "signed", "rejected")
# What the timeline records. The last four are recorded at a step by the person carrying the document.
TIMELINE_KINDS = ("created", "assigned", "step_added", "completed", "cancelled", "submitted", "returned", "signed", "rejected",
                  "handover_requested", "handover_accepted", "handover_declined", "handover_withdrawn")


class TrackedDocument(Base):
    __tablename__ = "tracked_documents"
    __table_args__ = (CheckConstraint(f"status IN {TRACKER_STATUSES}", name="tracked_documents_status_check"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    title: Mapped[str] = mapped_column(Text)
    reference_no: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    assigned_to: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(Text, server_default="in_progress")
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Deleting hides the document; it and its timeline stay in the database for the audit log.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    # A handover the carrier asked for, waiting for that person to accept.
    handover_to: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    handover_note: Mapped[str | None] = mapped_column(Text)
    handover_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TrackerStep(Base):
    """One signature the document needs, in order (AD, ED, PVC, VC, ...)."""
    __tablename__ = "tracked_document_steps"
    __table_args__ = (CheckConstraint(f"status IN {STEP_STATUSES}", name="tracked_document_steps_status_check"),
                      UniqueConstraint("document_id", "step_no", name="tracked_document_steps_no_key"))

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("tracked_documents.id"), index=True)
    step_no: Mapped[int] = mapped_column(Integer)
    authority: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default="pending")


class TrackerUpdate(Base):
    """One line of the timeline. Never changed or deleted."""
    __tablename__ = "tracked_document_updates"
    __table_args__ = (CheckConstraint(f"kind IN {TIMELINE_KINDS}", name="tracked_document_updates_kind_check"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("tracked_documents.id"), index=True)
    step_id: Mapped[int | None] = mapped_column(ForeignKey("tracked_document_steps.id"))
    kind: Mapped[str] = mapped_column(Text)
    happened_on: Mapped[date | None] = mapped_column(Date)
    note: Mapped[str | None] = mapped_column(Text)
    assigned_to: Mapped[int | None] = mapped_column(ForeignKey("users.id"))    # for 'created' and 'assigned'
    file_key: Mapped[str | None] = mapped_column(Text, unique=True)
    file_name: Mapped[str | None] = mapped_column(Text)
    file_type: Mapped[str | None] = mapped_column(Text)
    by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
