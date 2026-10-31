from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PermissionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    module: str
    description: str
    sensitive: bool


class RoleIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    description: str | None = Field(default=None, max_length=500)
    permissions: list[str] = Field(default_factory=list)
    reason: str = Field(min_length=3, max_length=500)


class RoleOut(BaseModel):
    id: int
    name: str
    description: str | None
    permissions: list[str]
    active_grant_count: int


class GrantIn(BaseModel):
    subject_type: Literal["user", "position", "department"]
    subject_id: int
    permission_code: str | None = None
    role_id: int | None = None
    scope_type: str = "global"
    scope_id: int | None = None
    expires_at: datetime | None = None
    reason: str = Field(min_length=3, max_length=500)

    @model_validator(mode="after")
    def _one_target(self):
        if (self.permission_code is None) == (self.role_id is None):
            raise ValueError("Provide exactly one of permission_code or role_id.")
        return self


class RevokeIn(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class GrantOut(BaseModel):
    id: int
    subject_type: str
    subject_id: int
    permission_code: str | None
    role_id: int | None
    role_name: str | None
    scope_type: str
    scope_id: int | None
    scope_name: str | None
    expires_at: datetime | None
    revoked_at: datetime | None
    granted_by: int
    granted_by_name: str | None
    reason: str
    created_at: datetime
    active: bool


class EffectiveOut(BaseModel):
    code: str
    scope_type: str
    scope_id: int | None
    via_role: str | None
    via_subject: str | None
    grant_id: int


class EffectiveAccessOut(BaseModel):
    all_permissions: bool
    permissions: list[EffectiveOut]


class PermissionAuditOut(BaseModel):
    id: int
    actor_id: int | None
    actor_name: str | None
    action: str
    subject_type: str | None
    subject_id: int | None
    subject_name: str | None
    permission_code: str | None
    role_id: int | None
    scope_type: str | None
    scope_id: int | None
    old_value: dict | None
    new_value: dict | None
    reason: str | None
    created_at: datetime
