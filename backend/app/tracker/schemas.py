from datetime import date, datetime

from pydantic import BaseModel, Field

from app.org.schemas import PersonRef


class TrackerIn(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    reference_no: str | None = Field(default=None, max_length=80)
    description: str | None = Field(default=None, max_length=2000)
    assigned_to: int
    steps: list[str] = Field(min_length=1, max_length=12)            # e.g. ["AD", "ED", "PVC", "VC"], in order


class AssignIn(BaseModel):
    user_id: int


class StepIn(BaseModel):
    authority: str = Field(min_length=1, max_length=60)


class CancelIn(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class StepOut(BaseModel):
    id: int
    step_no: int
    authority: str
    status: str


class TimelineOut(BaseModel):
    id: int
    kind: str
    step: str | None
    happened_on: date | None
    note: str | None
    assigned_to: PersonRef | None
    file_name: str | None
    by: PersonRef
    at: datetime


class TrackerOut(BaseModel):
    id: int
    title: str
    reference_no: str | None
    status: str
    assigned_to: PersonRef
    created_by: PersonRef
    created_at: datetime
    current_step: str | None
    steps_signed: int
    steps_total: int
    last_update_at: datetime


class TrackerDetailOut(TrackerOut):
    description: str | None
    steps: list[StepOut]
    timeline: list[TimelineOut]
    can_record: bool
    can_manage: bool                  # reassign and cancel
    can_add_step: bool


class AccessOut(BaseModel):
    sees_all: bool                    # the Chairperson, Vice Chairperson, Secretary and Joint Secretary


class FileUrlOut(BaseModel):
    url: str
