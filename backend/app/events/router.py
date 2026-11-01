from typing import Literal

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.deps import require_any, require_in_service
from app.core.db import get_db
from app.events import service
from app.events.models import EventChecklistItem, EventMilestone
from app.events.schemas import (ChecklistItemIn, EventDetailOut, EventIn, EventOut, MilestoneIn,
                                TeamMemberIn, TransitionIn)
from app.users.models import User

router = APIRouter(prefix="/api/events", tags=["events"])

# Event pages are also open to the event's owner and team, so most routes only require a
# signed-in user and the service checks events.view / events.edit or involvement.


@router.get("", response_model=list[EventOut])
def list_events(status: str | None = None, q: str | None = None,
                view: Literal["visible", "mine", "action", "all"] = "visible",
                user: User = Depends(require_in_service("events.view")), db: Session = Depends(get_db)):
    return service.summaries(db, service.list_events(db, user, status, q, view))


@router.post("", response_model=EventDetailOut, status_code=201)
def create_event(body: EventIn, actor: User = Depends(require_any("events.create")),
                 db: Session = Depends(get_db)):
    return service.detail(db, actor, service.create_event(db, actor, body).id)


@router.get("/{event_id}", response_model=EventDetailOut)
def get_event(event_id: int, user: User = Depends(require_in_service("events.view")),
              db: Session = Depends(get_db)):
    return service.detail(db, user, event_id)


@router.put("/{event_id}", response_model=EventDetailOut)
def update_event(event_id: int, body: EventIn, actor: User = Depends(require_in_service("events.edit")),
                 db: Session = Depends(get_db)):
    service.update_event(db, actor, event_id, body)
    return service.detail(db, actor, event_id)


@router.post("/{event_id}/transition", response_model=EventDetailOut)
def transition(event_id: int, body: TransitionIn, actor: User = Depends(require_in_service("events.edit")),
               db: Session = Depends(get_db)):
    service.transition(db, actor, event_id, body)
    return service.detail(db, actor, event_id)


@router.post("/{event_id}/team", response_model=EventDetailOut, status_code=201)
def add_team_member(event_id: int, body: TeamMemberIn, actor: User = Depends(require_in_service("events.edit")),
                    db: Session = Depends(get_db)):
    service.add_team_member(db, actor, event_id, body)
    return service.detail(db, actor, event_id)


@router.delete("/{event_id}/team/{member_id}", response_model=EventDetailOut)
def remove_team_member(event_id: int, member_id: int, actor: User = Depends(require_in_service("events.edit")),
                       db: Session = Depends(get_db)):
    service.remove_team_member(db, actor, event_id, member_id)
    return service.detail(db, actor, event_id)


@router.post("/{event_id}/milestones", response_model=EventDetailOut, status_code=201)
def add_milestone(event_id: int, body: MilestoneIn, actor: User = Depends(require_in_service("events.edit")),
                  db: Session = Depends(get_db)):
    service.save_milestone(db, actor, event_id, body)
    return service.detail(db, actor, event_id)


@router.put("/{event_id}/milestones/{item_id}", response_model=EventDetailOut)
def update_milestone(event_id: int, item_id: int, body: MilestoneIn,
                     actor: User = Depends(require_in_service("events.edit")), db: Session = Depends(get_db)):
    service.save_milestone(db, actor, event_id, body, item_id)
    return service.detail(db, actor, event_id)


@router.delete("/{event_id}/milestones/{item_id}", response_model=EventDetailOut)
def delete_milestone(event_id: int, item_id: int, actor: User = Depends(require_in_service("events.edit")),
                     db: Session = Depends(get_db)):
    service.delete_workspace_item(db, actor, event_id, EventMilestone, item_id)
    return service.detail(db, actor, event_id)


@router.post("/{event_id}/checklist", response_model=EventDetailOut, status_code=201)
def add_checklist_item(event_id: int, body: ChecklistItemIn,
                       actor: User = Depends(require_in_service("events.edit")), db: Session = Depends(get_db)):
    service.save_checklist_item(db, actor, event_id, body)
    return service.detail(db, actor, event_id)


@router.put("/{event_id}/checklist/{item_id}", response_model=EventDetailOut)
def update_checklist_item(event_id: int, item_id: int, body: ChecklistItemIn,
                          actor: User = Depends(require_in_service("events.edit")), db: Session = Depends(get_db)):
    service.save_checklist_item(db, actor, event_id, body, item_id)
    return service.detail(db, actor, event_id)


@router.delete("/{event_id}/checklist/{item_id}", response_model=EventDetailOut)
def delete_checklist_item(event_id: int, item_id: int, actor: User = Depends(require_in_service("events.edit")),
                          db: Session = Depends(get_db)):
    service.delete_workspace_item(db, actor, event_id, EventChecklistItem, item_id)
    return service.detail(db, actor, event_id)
