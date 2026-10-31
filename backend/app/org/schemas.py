from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.users.schemas import UserCreateIn, UserOut

StartReason = Literal["appointed", "promoted", "transferred", "reinstated"]
EndReason = Literal["promoted", "transferred", "resigned", "removed", "term_ended"]
Lifecycle = Literal["onboarding", "probation", "active", "alumni", "removed"]


class PersonRef(BaseModel):
    id: int
    full_name: str
    email: str


class DepartmentIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    description: str | None = Field(default=None, max_length=1000)
    parent_id: int | None = None


class DepartmentOut(BaseModel):
    id: int
    name: str
    description: str | None
    parent_id: int | None
    status: str
    member_count: int
    position_count: int
    vacant_positions: int
    leads: list[PersonRef]


class PositionIn(BaseModel):
    title: str = Field(min_length=2, max_length=80)
    description: str | None = Field(default=None, max_length=1000)
    department_id: int | None = None
    reports_to_position_id: int | None = None
    is_lead: bool = False
    is_deputy: bool = False
    max_holders: int = Field(default=1, ge=1, le=100)
    rank_order: int = Field(default=100, ge=0, le=10000)


class HolderOut(BaseModel):
    assignment_id: int
    user: PersonRef
    valid_from: date


class PositionOut(BaseModel):
    id: int
    title: str
    description: str | None
    department_id: int | None
    department_name: str | None
    reports_to_position_id: int | None
    is_lead: bool
    is_deputy: bool
    max_holders: int
    rank_order: int
    status: str
    holders: list[HolderOut]


class AssignIn(BaseModel):
    user_id: int
    valid_from: date | None = None
    start_reason: StartReason = "appointed"
    note: str | None = Field(default=None, max_length=500)


class EndAssignmentIn(BaseModel):
    end_reason: EndReason
    valid_to: date | None = None
    note: str | None = Field(default=None, max_length=500)


class TransferIn(BaseModel):
    to_position_id: int
    reason: Literal["promoted", "transferred"]
    effective: date | None = None
    note: str | None = Field(default=None, max_length=500)


class MemberIn(BaseModel):
    user_id: int
    valid_from: date | None = None


class NewMemberIn(UserCreateIn):
    """A brand-new account that joins the department, optionally into one of its positions."""
    position_id: int | None = None


class ReasonIn(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


EndMembershipIn = ReasonIn


class AssignmentOut(BaseModel):
    id: int
    user: PersonRef
    position_id: int
    position_title: str
    department_id: int | None
    department_name: str | None
    valid_from: date
    valid_to: date | None
    start_reason: str
    end_reason: str | None
    note: str | None


class MembershipOut(BaseModel):
    id: int
    user: PersonRef
    department_id: int
    department_name: str
    valid_from: date
    valid_to: date | None
    end_reason: str | None


class NewMemberOut(BaseModel):
    user: UserOut
    invite_url: str | None = None      # shown once; only the hash is stored
    membership: MembershipOut


class ProfileIn(BaseModel):
    uid: str | None = Field(default=None, max_length=40)
    phone: str | None = Field(default=None, max_length=20)
    branch: str | None = Field(default=None, max_length=80)
    year_of_study: int | None = Field(default=None, ge=1, le=6)
    joined_on: date | None = None
    lifecycle_status: Lifecycle | None = None
    responsibilities: str | None = Field(default=None, max_length=2000)


class SelfProfileIn(BaseModel):
    phone: str | None = Field(default=None, max_length=20)
    branch: str | None = Field(default=None, max_length=80)
    year_of_study: int | None = Field(default=None, ge=1, le=6)


class ProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    uid: str | None = None
    phone: str | None = None
    branch: str | None = None
    year_of_study: int | None = None
    joined_on: date | None = None
    lifecycle_status: str = "onboarding"
    responsibilities: str | None = None


class UserOrgOut(BaseModel):
    user: PersonRef
    profile: ProfileOut
    positions: list[AssignmentOut]      # current and past, newest first
    memberships: list[MembershipOut]


class ChartNode(BaseModel):
    position_id: int
    title: str
    department_id: int | None
    department_name: str | None
    reports_to_position_id: int | None
    is_lead: bool
    is_deputy: bool
    max_holders: int
    holders: list[PersonRef]


class TermIn(BaseModel):
    name: str = Field(min_length=2, max_length=40)
    starts_on: date
    ends_on: date
    is_current: bool = False

    @model_validator(mode="after")
    def _dates(self):
        if self.ends_on <= self.starts_on:
            raise ValueError("The term must end after it starts.")
        return self


class TermOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    starts_on: date
    ends_on: date
    is_current: bool


class DepartmentDetailOut(DepartmentOut):
    positions: list[PositionOut]
    members: list[MembershipOut]
    created_at: datetime
