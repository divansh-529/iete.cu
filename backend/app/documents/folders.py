"""The folders every event starts with (blueprint §8.2). Kept apart from the service so the events
module can use it without an import cycle."""
from sqlalchemy.orm import Session

from app.documents.models import Folder

EVENT_FOLDERS = ("01 Proposal", "02 Permissions & Approvals", "03 Venue & Logistics",
                 "04 Notices & Communications", "05 Duty Leave & Attendance", "06 Sponsorship & Budget",
                 "07 Event Execution", "08 Post-Event Records", "09 Final Report & Archive")


def create_event_folders(db: Session, event_id: int, actor_id: int) -> None:
    db.add_all(Folder(name=name, event_id=event_id, sort_order=i, created_by=actor_id)
               for i, name in enumerate(EVENT_FOLDERS, start=1))
