from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str
    user_type: str
    status: str
    must_change_password: bool
    is_super_admin: bool
    last_login_at: datetime | None
    created_at: datetime


class UserCreateIn(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=120)
    # default_password: the forum's standard first password (settings.default_member_password)
    credential: Literal["default_password", "temp_password", "invite"] = "default_password"
    temp_password: str | None = None   # required when credential == 'temp_password'


class UserCreateOut(BaseModel):
    user: UserOut
    invite_url: str | None = None      # shown once; only the hash is stored
    email_sent: bool = False           # welcome email with sign-in details
    default_password: str | None = None   # when credential == 'default_password', to pass on by hand
    login_url: str | None = None


class UserUpdateIn(BaseModel):
    email: EmailStr | None = None
    full_name: str | None = Field(default=None, min_length=2, max_length=120)


class DeleteUserIn(BaseModel):
    reason: str = Field(min_length=3, max_length=500)
    confirm_email: str = Field(max_length=320)     # must match the account's email


class UserDeletedOut(BaseModel):
    positions_ended: int
    memberships_ended: int
    grants_revoked: int
    tasks_unassigned: int
    events_still_owned: int


class StatusChangeIn(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class ResetPasswordIn(BaseModel):
    temp_password: str


class InviteOut(BaseModel):
    invite_url: str


class UserPage(BaseModel):
    items: list[UserOut]
    total: int
