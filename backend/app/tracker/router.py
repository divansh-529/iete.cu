from datetime import date

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile
from sqlalchemy.orm import Session

from app.auth.deps import require_in_service
from app.core.db import get_db
from app.core.errors import AppError, not_found
from app.documents.service import MAX_FILE_BYTES, MB
from app.tracker import service
from app.tracker.schemas import AccessOut, AssignIn, CancelIn, FileUrlOut, StepIn, TrackerDetailOut, TrackerIn, TrackerOut
from app.users.models import User

router = APIRouter(prefix="/api/tracker", tags=["tracker"])

# Anyone on the team may add a document; who sees and changes one goes by who carries it, who added
# it and the position held (see service.py), not by grants.


def _team(user: User = Depends(require_in_service("documents.view"))) -> User:
    if user.user_type != "team":
        raise not_found("Page")
    return user


@router.get("/access", response_model=AccessOut)
def access(user: User = Depends(_team), db: Session = Depends(get_db)):
    return {"sees_all": service.sees_every_document(db, user)}


@router.get("", response_model=list[TrackerOut])
def listing(view: str = "mine", status: str | None = None, user: User = Depends(_team), db: Session = Depends(get_db)):
    return service.listing(db, user, view, status)


@router.post("", response_model=TrackerDetailOut, status_code=201)
def create(body: TrackerIn, user: User = Depends(_team), db: Session = Depends(get_db)):
    doc = service.create(db, user, body)
    return service.detail(db, user, doc.id)


@router.get("/{document_id}", response_model=TrackerDetailOut)
def detail(document_id: int, user: User = Depends(_team), db: Session = Depends(get_db)):
    return service.detail(db, user, document_id)


@router.post("/{document_id}/updates", response_model=TrackerDetailOut)
def record(document_id: int, status: str = Form(), happened_on: date = Form(),
           note: str | None = Form(default=None, max_length=1000), file: UploadFile | None = File(default=None),
           user: User = Depends(_team), db: Session = Depends(get_db)):
    content = None
    if file is not None and file.filename:
        content = file.file.read(MAX_FILE_BYTES + 1)
        if len(content) > MAX_FILE_BYTES:
            raise AppError(413, "FILE_TOO_LARGE", f"This file is too large. The limit is {MAX_FILE_BYTES // MB} MB.")
    service.record(db, user, document_id, status, happened_on, note, file.filename if file else None, content)
    return service.detail(db, user, document_id)


@router.put("/{document_id}/assignee", response_model=TrackerDetailOut)
def reassign(document_id: int, body: AssignIn, user: User = Depends(_team), db: Session = Depends(get_db)):
    service.reassign(db, user, document_id, body.user_id)
    return service.detail(db, user, document_id)


@router.post("/{document_id}/steps", response_model=TrackerDetailOut)
def add_step(document_id: int, body: StepIn, user: User = Depends(_team), db: Session = Depends(get_db)):
    service.add_step(db, user, document_id, body.authority)
    return service.detail(db, user, document_id)


@router.post("/{document_id}/cancel", status_code=204)
def cancel(document_id: int, body: CancelIn, user: User = Depends(_team), db: Session = Depends(get_db)):
    service.cancel(db, user, document_id, body.reason)
    return Response(status_code=204)


@router.get("/{document_id}/updates/{update_id}/file", response_model=FileUrlOut)
def file_url(document_id: int, update_id: int, user: User = Depends(_team), db: Session = Depends(get_db)):
    return {"url": service.file_url(db, user, document_id, update_id)}
