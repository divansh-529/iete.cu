from typing import Any

from sqlalchemy.orm import Session

from app.audit.models import AuditEvent
from app.core.request_context import client_ip


def record(db: Session, actor_id: int | None, action: str, entity_type: str,
           entity_id: int | None = None, before: dict[str, Any] | None = None,
           after: dict[str, Any] | None = None) -> None:
    """Add an audit row to the current transaction. The caller commits."""
    db.add(AuditEvent(actor_id=actor_id, action=action, entity_type=entity_type,
                      entity_id=entity_id, before=before, after=after, ip=client_ip.get()))
