from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.events.schemas import DepartmentRef, StatusChangeOut
from app.org.schemas import PersonRef

Priority = Literal["low", "medium", "high", "urgent"]


class TaskIn(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    priority: Priority = "medium"
    due_at: datetime | None = None
    department_id: int | None = None
    event_id: int | None = None
    reviewer_id: int | None = None          # defaults to the person creating the task
    depends_on: list[int] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def _has_home(self):
        if self.department_id is None and self.event_id is None:
            raise ValueError("Choose a department or an event for this task.")
        return self


class TaskCreateIn(TaskIn):
    assignee_ids: list[int] = Field(default_factory=list, max_length=30)


class AssigneesIn(BaseModel):
    user_ids: list[int] = Field(max_length=30)


class SubmissionIn(BaseModel):
    note: str | None = Field(default=None, max_length=5000)
    link_url: str | None = Field(default=None, max_length=1000)

    @field_validator("link_url")
    @classmethod
    def _http_link(cls, v: str | None) -> str | None:
        v = (v or "").strip() or None
        if v and not v.lower().startswith(("http://", "https://")):
            raise ValueError("Links must start with http:// or https://")
        return v

    @model_validator(mode="after")
    def _has_evidence(self):
        self.note = (self.note or "").strip() or None
        if not self.note and not self.link_url:
            raise ValueError("Add a note or a link describing the work.")
        return self


class ReviewIn(BaseModel):
    outcome: Literal["accepted", "changes_requested", "rejected"]
    remarks: str | None = Field(default=None, max_length=2000)


class ReopenIn(BaseModel):
    remarks: str = Field(min_length=3, max_length=1000)


class CommentIn(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


class EventRef(BaseModel):
    id: int
    name: str


class TaskRef(BaseModel):
    id: int
    title: str
    status: str


class TaskOut(BaseModel):
    id: int
    title: str
    priority: str
    status: str
    due_at: datetime | None
    overdue: bool
    department: DepartmentRef | None
    event: EventRef | None
    assignees: list[PersonRef]
    reviewer: PersonRef | None
    created_at: datetime
    updated_at: datetime


class SubmissionOut(BaseModel):
    id: int
    submitted_by: PersonRef
    note: str | None
    link_url: str | None
    submitted_at: datetime
    review_outcome: str | None
    reviewed_by: PersonRef | None
    review_remarks: str | None
    reviewed_at: datetime | None


class CommentOut(BaseModel):
    id: int
    author: PersonRef
    body: str
    created_at: datetime


class TaskDetailOut(TaskOut):
    description: str | None
    created_by: PersonRef
    depends_on: list[TaskRef]
    blocked: bool                   # waiting on a dependency that is not completed
    submissions: list[SubmissionOut]
    comments: list[CommentOut]
    history: list[StatusChangeOut]
    actions: list[str]              # what this person can do: edit, assign, start, submit, review, reopen, comment
