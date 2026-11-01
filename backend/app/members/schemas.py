from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field

from app.events.schemas import DepartmentRef
from app.org.schemas import PersonRef


class ProposeMemberIn(BaseModel):
    email: EmailStr                     # the candidate's Gmail (or other) address
    full_name: str = Field(min_length=2, max_length=120)
    position_id: int | None = None
    note: str | None = Field(default=None, max_length=500)


class DecisionIn(BaseModel):
    remarks: str | None = Field(default=None, max_length=500)


class ProposalOut(BaseModel):
    id: int
    person: PersonRef
    account_status: str
    department: DepartmentRef
    position: DepartmentRef | None      # {id, name}
    note: str | None
    status: Literal["pending", "approved", "rejected"]
    proposed_by: PersonRef
    created_at: datetime
    decided_by: PersonRef | None
    decided_at: datetime | None
    decision_remarks: str | None
    email_sent_at: datetime | None
    can_decide: bool


class DecisionOut(BaseModel):
    proposal: ProposalOut
    email_sent: bool | None = None      # approve / resend: did the welcome email go out?
    login_url: str
    default_password: str               # shown to approvers so they can pass it on if email is off
