from pydantic import BaseModel, EmailStr

from app.users.schemas import UserOut


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class ChangePasswordIn(BaseModel):
    current_password: str | None = None   # not needed for the forced first-time change
    new_password: str


class AcceptInviteIn(BaseModel):
    token: str
    new_password: str


class InviteInfoOut(BaseModel):
    email: str
    full_name: str


class EffectivePermission(BaseModel):
    code: str
    scope_type: str
    scope_id: int | None


class MeOut(BaseModel):
    user: UserOut
    permissions: list[EffectivePermission]   # UI hints only; the API re-checks everything
    all_permissions: bool                   # true for the Super Admin
