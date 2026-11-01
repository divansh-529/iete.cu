"""Score cards (the Chairperson's design, 2026-11-01; replaces the per-event points plan).

The Chairperson opens a scoring round whenever they choose. Everyone except the Chairperson gets a
score card for the round, worth up to 20, filled in by fixed scorers according to their role (see
rules.py). When the Chairperson closes the round, the cards are published and everyone can see
everyone's. Totals add up across rounds (20, 40, 60, ...).
"""
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (BigInteger, CheckConstraint, DateTime, ForeignKey, Identity, Index, Numeric,
                        Text, UniqueConstraint, func, text)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

CATEGORIES = ("member", "lead", "joint_secretary", "secretary", "vice_chair")
SLOTS = ("lead", "joint_secretary", "secretary", "vice_chair", "chairperson")


class ScoreRound(Base):
    __tablename__ = "score_rounds"
    __table_args__ = (
        CheckConstraint("status IN ('open', 'closed')", name="score_rounds_status_check"),
        Index("score_rounds_one_open", text("(true)"), unique=True, postgresql_where=text("status = 'open'")),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    title: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default="open")
    term_id: Mapped[int | None] = mapped_column(ForeignKey("terms.id"))
    opened_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    closed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ScoreCard(Base):
    """One person in one round. Their role and department are fixed when the round opens."""
    __tablename__ = "score_cards"
    __table_args__ = (
        CheckConstraint(f"category IN {CATEGORIES}", name="score_cards_category_check"),
        UniqueConstraint("round_id", "user_id", name="score_cards_one_per_round"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    round_id: Mapped[int] = mapped_column(ForeignKey("score_rounds.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    category: Mapped[str] = mapped_column(Text)
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"))


class ScoreEntry(Base):
    """One scorer's marks on one card (their slot: lead, secretary, ...). Editable while the
    round is open; every save is audited."""
    __tablename__ = "score_entries"
    __table_args__ = (
        CheckConstraint(f"slot IN {SLOTS}", name="score_entries_slot_check"),
        CheckConstraint("points >= 0 AND points <= max_points", name="score_entries_range_check"),
        UniqueConstraint("card_id", "slot", name="score_entries_one_per_slot"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    card_id: Mapped[int] = mapped_column(ForeignKey("score_cards.id"), index=True)
    slot: Mapped[str] = mapped_column(Text)
    max_points: Mapped[Decimal] = mapped_column(Numeric(4, 1))
    points: Mapped[Decimal] = mapped_column(Numeric(4, 1))
    remarks: Mapped[str | None] = mapped_column(Text)
    scored_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    scored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(),
                                                onupdate=func.now())
