from datetime import datetime

from sqlalchemy import (BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Identity, Index,
                        Text, func, text)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

SUBJECT_TYPES = ("user", "role", "position", "department")
SCOPE_TYPES = ("global", "department", "event", "folder", "finance_account", "record")
PERMISSION_AUDIT_ACTIONS = ("grant", "revoke", "modify", "expire",
                            "role_create", "role_update", "role_delete")


class Permission(Base):
    __tablename__ = "permissions"

    code: Mapped[str] = mapped_column(Text, primary_key=True)
    module: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)
    sensitive: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    name: Mapped[str] = mapped_column(Text, unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RolePermission(Base):
    __tablename__ = "role_permissions"

    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True)
    permission_code: Mapped[str] = mapped_column(ForeignKey("permissions.code"), primary_key=True)


class Grant(Base):
    __tablename__ = "grants"
    __table_args__ = (
        CheckConstraint(f"subject_type IN {SUBJECT_TYPES}", name="grants_subject_type_check"),
        CheckConstraint(f"scope_type IN {SCOPE_TYPES}", name="grants_scope_type_check"),
        CheckConstraint("(permission_code IS NULL) <> (role_id IS NULL)", name="grants_perm_xor_role"),
        CheckConstraint("(scope_type = 'global') = (scope_id IS NULL)", name="grants_scope_id_check"),
        Index("grants_subject_active_idx", "subject_type", "subject_id",
              postgresql_where=text("revoked_at IS NULL")),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    subject_type: Mapped[str] = mapped_column(Text)
    subject_id: Mapped[int] = mapped_column(BigInteger)
    permission_code: Mapped[str | None] = mapped_column(ForeignKey("permissions.code"))
    role_id: Mapped[int | None] = mapped_column(ForeignKey("roles.id"))
    scope_type: Mapped[str] = mapped_column(Text, server_default="global")
    scope_id: Mapped[int | None] = mapped_column(BigInteger)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    granted_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PermissionAudit(Base):
    __tablename__ = "permission_audit"
    __table_args__ = (
        CheckConstraint(f"action IN {PERMISSION_AUDIT_ACTIONS}", name="permission_audit_action_check"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))  # null = system job
    action: Mapped[str] = mapped_column(Text)
    subject_type: Mapped[str | None] = mapped_column(Text)
    subject_id: Mapped[int | None] = mapped_column(BigInteger)
    permission_code: Mapped[str | None] = mapped_column(Text)
    role_id: Mapped[int | None] = mapped_column(BigInteger)
    scope_type: Mapped[str | None] = mapped_column(Text)
    scope_id: Mapped[int | None] = mapped_column(BigInteger)
    old_value: Mapped[dict | None] = mapped_column(JSONB)
    new_value: Mapped[dict | None] = mapped_column(JSONB)
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
