"""Document tracker (the Chairperson's request, 2026-11-12): a paper document carried by one person
from office to office for signatures, for example AD → ED → PVC → VC. The steps are chosen for each
document. Anyone on the team can add a document and assign anyone on the team to carry it. At the
current step, the person records Submitted, Returned with changes, Signed or Rejected, with the date,
a note and an optional photo or scan. Every record stays on the document's timeline.

Who sees a document: the person carrying it, whoever added it, and the Chairperson, Vice Chairperson,
Secretary and Joint Secretary (by position held). The same people record steps. Reassigning, adding
a step and cancelling are for whoever added it and those four; the carrier can also add a step,
because they are the one told at an office that another signature is needed.
"""
import uuid
from datetime import date, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.audit import service as audit
from app.core.errors import AppError, forbidden, not_found
from app.core.time import utcnow
from app.documents import storage
from app.documents.service import PREVIEWABLE, check_file
from app.notifications.service import notify
from app.org.roster import sees_all
from app.org.service import people_by_id
from app.tracker.models import TrackedDocument, TrackerStep, TrackerUpdate
from app.tracker.schemas import TrackerIn
from app.users.models import User

FILE_TYPES = (".pdf", ".jpg", ".jpeg", ".png")
STEP_RECORDS = ("submitted", "returned", "signed", "rejected")
IST = timedelta(hours=5, minutes=30)


def _today() -> date:
    return (utcnow() + IST).date()


def _team_member(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None or user.user_type != "team" or user.status not in ("active", "invited"):
        raise AppError(422, "INVALID_PERSON", "Choose someone on the team.")
    return user


def _can_see(db: Session, user: User, doc: TrackedDocument) -> bool:
    return user.id in (doc.assigned_to, doc.created_by) or sees_all(db, user)


def _can_manage(db: Session, user: User, doc: TrackedDocument) -> bool:
    return user.id == doc.created_by or sees_all(db, user)


def _get(db: Session, user: User, document_id: int) -> TrackedDocument:
    doc = db.get(TrackedDocument, document_id)
    if doc is None or not _can_see(db, user, doc):
        raise not_found("Document")
    return doc


def _open(doc: TrackedDocument) -> None:
    if doc.status != "in_progress":
        raise AppError(409, "INVALID_STATE", "This document is closed, so it can't change.")


def _steps(db: Session, document_id: int) -> list[TrackerStep]:
    return list(db.scalars(select(TrackerStep).where(TrackerStep.document_id == document_id).order_by(TrackerStep.step_no)))


def _current(steps: list[TrackerStep]) -> TrackerStep | None:
    return next((s for s in steps if s.status != "signed"), None)


def _clean(text: str | None) -> str | None:
    return (text or "").strip() or None


def _tell(db: Session, doc: TrackedDocument, actor: User, kind: str, **extra) -> None:
    notify(db, {doc.assigned_to, doc.created_by}, kind,
           {"document_id": doc.id, "title": doc.title, "by": actor.full_name, **extra}, actor.id)


# ---------------------------------------------------------------- changes

def create(db: Session, actor: User, body: TrackerIn) -> TrackedDocument:
    steps = [s.strip() for s in body.steps if s.strip()]
    if not steps:
        raise AppError(422, "STEPS_REQUIRED", "Add at least one signature step, such as AD.")
    if any(len(s) > 60 for s in steps):
        raise AppError(422, "VALIDATION_ERROR", "Each step's name can be at most 60 characters.")
    assignee = _team_member(db, body.assigned_to)
    doc = TrackedDocument(title=body.title.strip(), reference_no=_clean(body.reference_no),
                          description=_clean(body.description), assigned_to=assignee.id, created_by=actor.id)
    db.add(doc)
    db.flush()
    db.add_all(TrackerStep(document_id=doc.id, step_no=i, authority=s) for i, s in enumerate(steps, start=1))
    db.add(TrackerUpdate(document_id=doc.id, kind="created", assigned_to=assignee.id, by=actor.id,
                         note=" → ".join(steps)))
    audit.record(db, actor.id, "tracker.create", "tracked_document", doc.id,
                 after={"title": doc.title, "assigned_to": assignee.id, "steps": steps})
    notify(db, [assignee.id], "tracker.assigned", {"document_id": doc.id, "title": doc.title, "by": actor.full_name}, actor.id)
    db.commit()
    return doc


def record(db: Session, actor: User, document_id: int, status: str, happened_on: date, note: str | None,
           filename: str | None, content: bytes | None) -> None:
    doc = _get(db, actor, document_id)
    _open(doc)
    if status not in STEP_RECORDS:
        raise AppError(422, "VALIDATION_ERROR", "Choose Submitted, Returned with changes, Signed or Rejected.")
    if happened_on > _today():
        raise AppError(422, "FUTURE_DATE", "The date can't be in the future.")
    note = _clean(note)
    if status in ("returned", "rejected") and not note:
        raise AppError(422, "NOTE_REQUIRED", "Please say what the office asked for, or why it was rejected.")
    steps = _steps(db, doc.id)
    step = _current(steps)
    update = TrackerUpdate(document_id=doc.id, step_id=step.id, kind=status, happened_on=happened_on, note=note, by=actor.id)
    if content:
        name, extension, mime_type = check_file(filename or "", content)
        if extension not in FILE_TYPES:
            raise AppError(422, "FILE_TYPE", "Attach a photo (JPG or PNG) or a PDF scan.")
        update.file_key, update.file_name, update.file_type = f"tracker/{uuid.uuid4().hex}{extension}", name, mime_type
        storage.put(update.file_key, content, mime_type)
    step.status = status
    db.add(update)
    if status == "rejected" or (status == "signed" and _current(steps) is None):
        doc.status, doc.closed_at = ("rejected" if status == "rejected" else "completed"), utcnow()
        if doc.status == "completed":
            db.add(TrackerUpdate(document_id=doc.id, kind="completed", happened_on=happened_on, by=actor.id))
    audit.record(db, actor.id, "tracker.record", "tracked_document", doc.id,
                 after={"step": step.authority, "status": status, "on": happened_on.isoformat(), "note": note,
                        "file": update.file_name})
    _tell(db, doc, actor, "tracker.updated", step=step.authority, status=status, done=doc.status == "completed")
    db.commit()


def reassign(db: Session, actor: User, document_id: int, user_id: int) -> None:
    doc = _get(db, actor, document_id)
    if not _can_manage(db, actor, doc):
        raise forbidden("Only whoever added this document, or the leaders, can reassign it.")
    _open(doc)
    person = _team_member(db, user_id)
    if person.id == doc.assigned_to:
        return
    before = doc.assigned_to
    doc.assigned_to = person.id
    db.add(TrackerUpdate(document_id=doc.id, kind="assigned", assigned_to=person.id, by=actor.id))
    audit.record(db, actor.id, "tracker.assign", "tracked_document", doc.id, before={"assigned_to": before},
                 after={"assigned_to": person.id})
    notify(db, [person.id], "tracker.assigned", {"document_id": doc.id, "title": doc.title, "by": actor.full_name}, actor.id)
    db.commit()


def add_step(db: Session, actor: User, document_id: int, authority: str) -> None:
    doc = _get(db, actor, document_id)
    if not (_can_manage(db, actor, doc) or actor.id == doc.assigned_to):
        raise forbidden()
    _open(doc)
    authority = authority.strip()
    if not authority:
        raise AppError(422, "VALIDATION_ERROR", "Name the office, such as Dean.")
    last = db.scalar(select(func.max(TrackerStep.step_no)).where(TrackerStep.document_id == doc.id)) or 0
    db.add(TrackerStep(document_id=doc.id, step_no=last + 1, authority=authority))
    db.add(TrackerUpdate(document_id=doc.id, kind="step_added", note=authority, by=actor.id))
    audit.record(db, actor.id, "tracker.add_step", "tracked_document", doc.id, after={"step": authority})
    db.commit()


def cancel(db: Session, actor: User, document_id: int, reason: str) -> None:
    doc = _get(db, actor, document_id)
    if not _can_manage(db, actor, doc):
        raise forbidden("Only whoever added this document, or the leaders, can cancel it.")
    _open(doc)
    doc.status, doc.closed_at = "cancelled", utcnow()
    db.add(TrackerUpdate(document_id=doc.id, kind="cancelled", note=reason.strip(), by=actor.id))
    audit.record(db, actor.id, "tracker.cancel", "tracked_document", doc.id, after={"reason": reason.strip()})
    _tell(db, doc, actor, "tracker.cancelled", reason=reason.strip())
    db.commit()


def file_url(db: Session, user: User, document_id: int, update_id: int) -> str:
    doc = _get(db, user, document_id)
    update = db.get(TrackerUpdate, update_id)
    if update is None or update.document_id != doc.id or not update.file_key:
        raise not_found("File")
    return storage.presigned_url(update.file_key, update.file_name, update.file_type, update.file_type in PREVIEWABLE)


# ---------------------------------------------------------------- reading

def _summaries(db: Session, docs: list[TrackedDocument]) -> list[dict]:
    ids = [d.id for d in docs] or [0]
    steps: dict[int, list[TrackerStep]] = {d.id: [] for d in docs}
    for s in db.scalars(select(TrackerStep).where(TrackerStep.document_id.in_(ids)).order_by(TrackerStep.step_no)):
        steps[s.document_id].append(s)
    last = dict(db.execute(select(TrackerUpdate.document_id, func.max(TrackerUpdate.at))
                           .where(TrackerUpdate.document_id.in_(ids)).group_by(TrackerUpdate.document_id)).all())
    people = people_by_id(db, {d.assigned_to for d in docs} | {d.created_by for d in docs})
    out = []
    for d in docs:
        current = _current(steps[d.id]) if d.status == "in_progress" else None
        out.append({"id": d.id, "title": d.title, "reference_no": d.reference_no, "status": d.status,
                    "assigned_to": people[d.assigned_to], "created_by": people[d.created_by], "created_at": d.created_at,
                    "current_step": current.authority if current else None,
                    "steps_signed": sum(1 for s in steps[d.id] if s.status == "signed"), "steps_total": len(steps[d.id]),
                    "last_update_at": last.get(d.id, d.created_at)})
    return out


def listing(db: Session, user: User, view: str, status: str | None) -> list[dict]:
    stmt = select(TrackedDocument)
    if view != "all" or not sees_all(db, user):
        stmt = stmt.where(or_(TrackedDocument.assigned_to == user.id, TrackedDocument.created_by == user.id))
    if status:
        stmt = stmt.where(TrackedDocument.status == status)
    docs = list(db.scalars(stmt.order_by(TrackedDocument.id.desc()).limit(300)))
    return sorted(_summaries(db, docs), key=lambda d: (d["status"] != "in_progress", -d["last_update_at"].timestamp()))


def detail(db: Session, user: User, document_id: int) -> dict:
    doc = _get(db, user, document_id)
    steps = _steps(db, doc.id)
    names = {s.id: s.authority for s in steps}
    updates = list(db.scalars(select(TrackerUpdate).where(TrackerUpdate.document_id == doc.id)
                              .order_by(TrackerUpdate.at, TrackerUpdate.id)))
    people = people_by_id(db, {u.by for u in updates} | {u.assigned_to for u in updates})
    timeline = [{"id": u.id, "kind": u.kind, "step": names.get(u.step_id), "happened_on": u.happened_on, "note": u.note,
                 "assigned_to": people.get(u.assigned_to), "file_name": u.file_name, "by": people[u.by], "at": u.at}
                for u in updates]
    open_ = doc.status == "in_progress"
    return {**_summaries(db, [doc])[0], "description": doc.description,
            "steps": [{"id": s.id, "step_no": s.step_no, "authority": s.authority, "status": s.status} for s in steps],
            "timeline": timeline, "can_record": open_, "can_manage": open_ and _can_manage(db, user, doc),
            "can_add_step": open_ and (_can_manage(db, user, doc) or user.id == doc.assigned_to)}


def sees_every_document(db: Session, user: User) -> bool:
    return sees_all(db, user)
