from datetime import datetime

from sqlalchemy import (BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Identity,
                        Index, Integer, LargeBinary, Text, func, text)
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

# proposed: recruited by a lead, waiting for approval (cannot sign in). rejected: the proposal was
# turned down; the row stays so the decision remains on record.
USER_STATUSES = ("proposed", "rejected", "invited", "active", "suspended", "deactivated")
USER_TYPES = ("team", "participant")


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(f"user_type IN {USER_TYPES}", name="users_user_type_check"),
        CheckConstraint(f"status IN {USER_STATUSES}", name="users_status_check"),
        Index("one_super_admin", text("(true)"), unique=True,
              postgresql_where=text("is_super_admin")),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    email: Mapped[str] = mapped_column(CITEXT, unique=True)
    full_name: Mapped[str] = mapped_column(Text)
    password_hash: Mapped[str | None] = mapped_column(Text)
    user_type: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default="invited")
    must_change_password: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    is_super_admin: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    failed_login_count: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(),
                                                 onupdate=func.now())


class InviteToken(Base):
    __tablename__ = "invite_tokens"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    token_hash: Mapped[bytes] = mapped_column(LargeBinary, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
