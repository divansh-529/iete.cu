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
    credential: Literal["temp_password", "invite"]
    temp_password: str | None = None   # required when credential == 'temp_password'


class UserCreateOut(BaseModel):
    user: UserOut
    invite_url: str | None = None      # shown once; only the hash is stored


class UserUpdateIn(BaseModel):
    email: EmailStr | None = None
    full_name: str | None = Field(default=None, min_length=2, max_length=120)


class StatusChangeIn(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class ResetPasswordIn(BaseModel):
    temp_password: str


class InviteOut(BaseModel):
    invite_url: str


class UserPage(BaseModel):
    items: list[UserOut]
    total: int
