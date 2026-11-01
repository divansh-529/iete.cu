"""Recruitment proposals. A lead proposes a new member for their department; the Chairperson,
Vice Chairperson or Secretary approves (the account is activated and the candidate emailed) or
rejects it. Every proposal and decision stays on record."""
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Identity, Index, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

PROPOSAL_STATUSES = ("pending", "approved", "rejected")


class MemberProposal(Base):
    __tablename__ = "member_proposals"
    __table_args__ = (
        CheckConstraint(f"status IN {PROPOSAL_STATUSES}", name="mp_status_check"),
        CheckConstraint("(status = 'pending') = (decided_at IS NULL)", name="mp_decided_check"),
        Index("member_proposals_one_pending", "user_id", unique=True, postgresql_where=text("status = 'pending'")),
        Index("member_proposals_status_idx", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.id"))
    position_id: Mapped[int | None] = mapped_column(ForeignKey("positions.id"))
    note: Mapped[str | None] = mapped_column(Text)               # from the proposer
    status: Mapped[str] = mapped_column(Text, server_default="pending")
    proposed_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_remarks: Mapped[str | None] = mapped_column(Text)
    email_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
