from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, Index, Text, func
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index("audit_events_entity_idx", "entity_type", "entity_id"),
        Index("audit_events_actor_idx", "actor_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(Text)            # e.g. 'user.create', 'auth.login'
    entity_type: Mapped[str] = mapped_column(Text)
    entity_id: Mapped[int | None] = mapped_column(BigInteger)
    before: Mapped[dict | None] = mapped_column(JSONB)
    after: Mapped[dict | None] = mapped_column(JSONB)
    ip: Mapped[str | None] = mapped_column(INET)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
