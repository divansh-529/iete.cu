from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.events.schemas import DepartmentRef
from app.org.schemas import PersonRef


class RoundIn(BaseModel):
    title: str = Field(min_length=3, max_length=80)          # e.g. "November 2026"


class DeleteRoundIn(BaseModel):
    reason: str = Field(min_length=3, max_length=500)
    confirm: str = Field(max_length=80)                      # the round's title, or RESET for all rounds


class ResetOut(BaseModel):
    rounds_deleted: int


class EntryIn(BaseModel):
    points: Decimal = Field(ge=0, le=10, multiple_of=Decimal("0.5"))
    remarks: str | None = Field(default=None, max_length=500)


class RoundOut(BaseModel):
    id: int
    title: str
    status: str
    opened_at: datetime
    closed_at: datetime | None
    cards: int
    entries_given: int
    entries_expected: int


class SlotOut(BaseModel):
    slot: str
    label: str
    max_points: Decimal
    points: Decimal | None            # hidden (None) from others while the round is open
    remarks: str | None
    scored_by: PersonRef | None
    given: bool
    editable: bool


class CardOut(BaseModel):
    card_id: int
    person: PersonRef
    category: str
    category_label: str
    department: DepartmentRef | None
    slots: list[SlotOut]
    total: Decimal
    max_total: Decimal


class ToScoreOut(BaseModel):
    round: RoundOut
    cards: list[CardOut]
    my_given: int
    my_expected: int


class PublishedCardOut(CardOut):
    round_id: int
    round_title: str
    closed_at: datetime | None


class PersonScoresOut(BaseModel):
    person: PersonRef
    cards: list[PublishedCardOut]
    total: Decimal
    max_total: Decimal


class LeaderboardRow(BaseModel):
    person: PersonRef
    category_label: str
    department: str | None
    rounds: int
    total: Decimal
    max_total: Decimal
    latest: Decimal
