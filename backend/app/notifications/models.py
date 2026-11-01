"""In-app notifications. There is no email at launch (docs/07-open-decisions.md); the portal
polls for unread ones."""
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, Index, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        Index("notifications_unread_idx", "user_id", postgresql_where=text("read_at IS NULL")),
        Index("notifications_user_created_idx", "user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    kind: Mapped[str] = mapped_column(Text)        # 'task.assigned', 'event.status', ...
    payload: Mapped[dict] = mapped_column(JSONB)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
