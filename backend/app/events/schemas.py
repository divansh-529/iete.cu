from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

from app.org.schemas import PersonRef


class EventIn(BaseModel):
    name: str = Field(min_length=3, max_length=120)
    category: str | None = Field(default=None, max_length=60)
    description: str | None = Field(default=None, max_length=5000)
    venue: str | None = Field(default=None, max_length=200)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    capacity: int | None = Field(default=None, ge=1, le=100000)
    budget_planned: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    is_public: bool = False
    department_ids: list[int] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def _dates(self):
        if self.starts_at and self.ends_at and self.ends_at < self.starts_at:
            raise ValueError("The event cannot end before it starts.")
        return self


class TransitionIn(BaseModel):
    to_status: str
    remarks: str | None = Field(default=None, max_length=1000)


class TeamMemberIn(BaseModel):
    user_id: int
    event_role: str = Field(min_length=2, max_length=40)


class MilestoneIn(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    due_at: datetime | None = None
    done: bool = False


class ChecklistItemIn(BaseModel):
    label: str = Field(min_length=2, max_length=200)
    done: bool = False


class DepartmentRef(BaseModel):
    id: int
    name: str


class AllowedTransition(BaseModel):
    to_status: str
    label: str
    needs_remarks: bool
    tone: str                    # 'primary' | 'secondary' | 'danger'


class EventOut(BaseModel):
    id: int
    name: str
    slug: str
    category: str | None
    status: str
    venue: str | None
    starts_at: datetime | None
    ends_at: datetime | None
    owner: PersonRef
    departments: list[DepartmentRef]
    team_size: int
    open_tasks: int
    created_at: datetime


class TeamMemberOut(BaseModel):
    id: int
    user: PersonRef
    event_role: str
    added_at: datetime


class MilestoneOut(BaseModel):
    id: int
    title: str
    due_at: datetime | None
    done_at: datetime | None


class ChecklistItemOut(BaseModel):
    id: int
    label: str
    sort_order: int
    done_at: datetime | None
    done_by: PersonRef | None


class StatusChangeOut(BaseModel):
    from_status: str | None
    to_status: str
    changed_by: PersonRef
    remarks: str | None
    changed_at: datetime


class EventDetailOut(EventOut):
    description: str | None
    capacity: int | None
    budget_planned: Decimal | None
    is_public: bool
    team: list[TeamMemberOut]
    milestones: list[MilestoneOut]
    checklist: list[ChecklistItemOut]
    history: list[StatusChangeOut]
    allowed_transitions: list[AllowedTransition]
    can_edit: bool               # change the event's details
    can_manage: bool             # team, milestones and checklist
    can_add_tasks: bool
