"""Folders, documents, versions and review. An event's owner and team work in its folders without
extra grants; everyone else needs the documents.* permission at the event's scope. The forum's own
folders (no event) need the permission globally."""
import hashlib
import uuid
from dataclasses import dataclass
from pathlib import PurePath

from sqlalchemy import func, or_, select, true
from sqlalchemy.orm import Session

from app.audit import service as audit
from app.core.errors import AppError, forbidden, not_found
from app.core.time import utcnow
from app.documents import storage
from app.documents.models import Document, DocumentReview, DocumentVersion, Folder
from app.documents.schemas import FolderIn, FolderRenameIn, ReviewIn
from app.events.models import Event, EventDepartment, EventTeamMember
from app.events.service import _on_team, event_scope
from app.notifications.service import notify
from app.permissions import engine
from app.permissions.engine import GLOBAL, Scope, can, visible_department_ids
from app.users.models import User

MB = 1024 * 1024
MAX_FILE_BYTES = 15 * MB
MAX_IMAGE_BYTES = 5 * MB
OFFICE_ZIP = b"PK\x03\x04"
# extension -> (type we store, what the file must start with). The browser's claimed type is ignored.
ALLOWED_TYPES = {
    ".pdf": ("application/pdf", b"%PDF-"),
    ".docx": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", OFFICE_ZIP),
    ".xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", OFFICE_ZIP),
    ".pptx": ("application/vnd.openxmlformats-officedocument.presentationml.presentation", OFFICE_ZIP),
    ".zip": ("application/zip", OFFICE_ZIP),
    ".jpg": ("image/jpeg", b"\xff\xd8\xff"),
    ".jpeg": ("image/jpeg", b"\xff\xd8\xff"),
    ".png": ("image/png", b"\x89PNG\r\n\x1a\n"),
}
PREVIEWABLE = {"application/pdf", "image/jpeg", "image/png"}
# from -> statuses a reviewer can move a document to. Draft -> submitted belongs to the uploaders.
REVIEW_STEPS = {"submitted": ("approved", "rejected"), "approved": ("final",), "final": ("archived",)}
LOCKED = ("final", "archived")


# ---------------------------------------------------------------- access

@dataclass
class Access:
    event: Event | None
    scope: Scope
    view: bool
    upload: bool
    manage: bool


def _access(db: Session, user: User, event_id: int | None) -> Access:
    if event_id is None:
        ev, scope, owner, team = None, GLOBAL, False, False
    else:
        ev = db.get(Event, event_id)
        if ev is None:
            raise not_found("Event")
        scope = event_scope(db, ev.id)
        owner = ev.owner_id == user.id
        team = _on_team(db, user.id, ev.id)
    return Access(ev, scope,
                  view=owner or team or can(db, user, "documents.view", scope),
                  upload=owner or team or can(db, user, "documents.upload", scope),
                  manage=owner or can(db, user, "documents.manage_folders", scope))


def _folder(db: Session, user: User, folder_id: int) -> tuple[Folder, Access]:
    folder = db.get(Folder, folder_id)
    if folder is None:
        raise not_found("Folder")
    access = _access(db, user, folder.event_id)
    if not access.view:
        raise not_found("Folder")
    return folder, access


def _document(db: Session, user: User, document_id: int) -> tuple[Document, Folder, Access]:
    doc = db.get(Document, document_id)
    if doc is None or doc.deleted_at is not None:
        raise not_found("Document")
    folder = db.get(Folder, doc.folder_id)
    access = _access(db, user, folder.event_id)
    if not access.view:
        raise not_found("Document")
    return doc, folder, access


def _reviewable(db: Session, user: User, doc: Document, access: Access) -> list[str]:
    if not can(db, user, "documents.review", access.scope):
        return []
    if _current_version(db, doc.id).uploaded_by == user.id and not user.is_super_admin:
        return []   # nobody reviews their own upload
    return list(REVIEW_STEPS.get(doc.status, ()))


def _allowed_reviews(db: Session, user: User, doc: Document, access: Access) -> list[str]:
    own = ["submitted"] if doc.status == "draft" and access.upload else []
    return own + _reviewable(db, user, doc, access)


# ---------------------------------------------------------------- folders

def _in_home(event_id: int | None):
    return Folder.event_id == event_id if event_id else Folder.event_id.is_(None)


def list_folders(db: Session, user: User, event_id: int | None) -> dict:
    access = _access(db, user, event_id)
    if not access.view:
        raise not_found("Event") if event_id else forbidden()
    count = (select(func.count()).select_from(Document)
             .where(Document.folder_id == Folder.id, Document.deleted_at.is_(None)).scalar_subquery())
    rows = db.execute(select(Folder, count).where(_in_home(event_id)).order_by(Folder.sort_order, Folder.name)).all()
    return {"folders": [{"id": f.id, "name": f.name, "document_count": n} for f, n in rows],
            "can_upload": access.upload, "can_manage": access.manage}


def create_folder(db: Session, actor: User, body: FolderIn) -> None:
    access = _access(db, actor, body.event_id)
    if not access.manage:
        raise forbidden()
    last = db.scalar(select(func.max(Folder.sort_order)).where(_in_home(body.event_id))) or 0
    folder = Folder(name=body.name.strip(), event_id=body.event_id, sort_order=last + 1, created_by=actor.id)
    db.add(folder)
    db.flush()
    audit.record(db, actor.id, "folder.create", "folder", folder.id, after={"name": folder.name, "event_id": body.event_id})
    db.commit()


def rename_folder(db: Session, actor: User, folder_id: int, body: FolderRenameIn) -> None:
    folder, access = _folder(db, actor, folder_id)
    if not access.manage:
        raise forbidden()
    before = {"name": folder.name}
    folder.name = body.name.strip()
    audit.record(db, actor.id, "folder.rename", "folder", folder.id, before=before, after={"name": folder.name})
    db.commit()


def delete_folder(db: Session, actor: User, folder_id: int) -> None:
    folder, access = _folder(db, actor, folder_id)
    if not access.manage:
        raise forbidden()
    # Deleted documents count too: their versions and history must stay reachable.
    if db.scalar(select(Document.id).where(Document.folder_id == folder.id).limit(1)):
        raise AppError(409, "FOLDER_IN_USE", "This folder has documents, so it can't be deleted.")
    audit.record(db, actor.id, "folder.delete", "folder", folder.id, before={"name": folder.name})
    db.delete(folder)
    db.commit()


# ---------------------------------------------------------------- upload

def check_file(filename: str, content: bytes) -> tuple[str, str, str]:
    """Refuses anything that isn't an allowed file. Returns its clean name, extension and type."""
    name = PurePath((filename or "").replace("\\", "/")).name.strip()
    extension = PurePath(name).suffix.lower()
    if extension not in ALLOWED_TYPES:
        raise AppError(422, "FILE_TYPE", "Only PDF, DOCX, XLSX, PPTX, JPG, PNG and ZIP files can be uploaded.")
    mime_type, signature = ALLOWED_TYPES[extension]
    if not content:
        raise AppError(422, "FILE_EMPTY", "This file is empty.")
    limit = MAX_IMAGE_BYTES if mime_type.startswith("image/") else MAX_FILE_BYTES
    if len(content) > limit:
        raise AppError(413, "FILE_TOO_LARGE", f"This file is too large. The limit is {limit // MB} MB.")
    if not content.startswith(signature):
        raise AppError(422, "FILE_CONTENT", f"This file is not a real {extension[1:].upper()} file.")
    return name, extension, mime_type


def _store_version(db: Session, actor: User, doc: Document, filename: str, content: bytes) -> DocumentVersion:
    name, extension, mime_type = check_file(filename, content)
    last = db.scalar(select(func.max(DocumentVersion.version_no)).where(DocumentVersion.document_id == doc.id)) or 0
    version = DocumentVersion(document_id=doc.id, version_no=last + 1, storage_key=f"documents/{uuid.uuid4().hex}{extension}",
                              original_filename=name, mime_type=mime_type, size_bytes=len(content),
                              sha256=hashlib.sha256(content).digest(), uploaded_by=actor.id)
    storage.put(version.storage_key, content, mime_type)
    db.add(version)
    db.flush()
    return version


def upload(db: Session, actor: User, folder_id: int, title: str, category: str | None, description: str | None,
           filename: str, content: bytes) -> Document:
    folder, access = _folder(db, actor, folder_id)
    if not access.upload:
        raise forbidden()
    title = title.strip()
    if not title:
        raise AppError(422, "TITLE_REQUIRED", "Please give the document a title.")
    doc = Document(folder_id=folder.id, title=title, category=(category or "").strip() or None,
                   description=(description or "").strip() or None, created_by=actor.id)
    db.add(doc)
    db.flush()
    version = _store_version(db, actor, doc, filename, content)
    audit.record(db, actor.id, "document.upload", "document", doc.id,
                 after={"title": doc.title, "folder": folder.name, "file": version.original_filename, "version": 1})
    db.commit()
    return doc


def add_version(db: Session, actor: User, document_id: int, filename: str, content: bytes) -> Document:
    doc, _, access = _document(db, actor, document_id)
    if not access.upload:
        raise forbidden()
    if doc.status in LOCKED:
        raise AppError(409, "DOCUMENT_LOCKED", "This document is final, so it can't be replaced.")
    version = _store_version(db, actor, doc, filename, content)
    before = doc.status
    doc.status = "draft"   # new content has not been reviewed
    if before != "draft":
        db.add(DocumentReview(document_id=doc.id, from_status=before, to_status="draft", reviewer_id=actor.id,
                              remarks=f"New version {version.version_no} uploaded"))
    audit.record(db, actor.id, "document.new_version", "document", doc.id,
                 after={"file": version.original_filename, "version": version.version_no})
    db.commit()
    return doc


# ---------------------------------------------------------------- review, download, delete

def review(db: Session, actor: User, document_id: int, body: ReviewIn) -> Document:
    doc, folder, access = _document(db, actor, document_id)
    if body.to_status not in _allowed_reviews(db, actor, doc, access):
        raise forbidden("You can't make this change to the document.")
    remarks = (body.remarks or "").strip() or None
    if body.to_status == "rejected" and not remarks:
        raise AppError(422, "REMARKS_REQUIRED", "Please say why the document is rejected.")
    before = doc.status
    doc.status = body.to_status
    db.add(DocumentReview(document_id=doc.id, from_status=before, to_status=body.to_status, remarks=remarks,
                          reviewer_id=actor.id))
    audit.record(db, actor.id, "document.review", "document", doc.id, before={"status": before},
                 after={"status": body.to_status, "remarks": remarks})
    payload = {"document_id": doc.id, "title": doc.title, "by": actor.full_name, "to_status": body.to_status,
               "remarks": remarks, "event_id": folder.event_id}
    if body.to_status == "submitted":
        notify(db, engine.users_who_can(db, "documents.review", access.scope, {actor.id}), "document.submitted", payload, actor.id)
    else:
        notify(db, [_current_version(db, doc.id).uploaded_by], "document.reviewed", payload, actor.id)
    db.commit()
    return doc


def download_url(db: Session, user: User, document_id: int, version_id: int | None, inline: bool) -> str:
    doc, _, _ = _document(db, user, document_id)
    version = db.get(DocumentVersion, version_id) if version_id else _current_version(db, doc.id)
    if version is None or version.document_id != doc.id:
        raise not_found("Version")
    return storage.presigned_url(version.storage_key, version.original_filename, version.mime_type,
                                 inline and version.mime_type in PREVIEWABLE)


def soft_delete(db: Session, actor: User, document_id: int) -> None:
    doc, folder, access = _document(db, actor, document_id)
    engine.ensure(db, actor, "documents.delete", access.scope)
    doc.deleted_at, doc.deleted_by = utcnow(), actor.id
    audit.record(db, actor.id, "document.delete", "document", doc.id,
                 before={"title": doc.title, "folder": folder.name, "status": doc.status})
    db.commit()


# ---------------------------------------------------------------- reading

def _current_version(db: Session, document_id: int) -> DocumentVersion:
    return db.scalar(select(DocumentVersion).where(DocumentVersion.document_id == document_id)
                     .order_by(DocumentVersion.version_no.desc()).limit(1))


def _person(db: Session, user_id: int) -> dict:
    u = db.get(User, user_id)
    return {"id": u.id, "full_name": u.full_name, "email": u.email}


def _version_view(db: Session, v: DocumentVersion) -> dict:
    return {"id": v.id, "version_no": v.version_no, "original_filename": v.original_filename, "mime_type": v.mime_type,
            "size_bytes": v.size_bytes, "uploaded_by": _person(db, v.uploaded_by), "uploaded_at": v.uploaded_at}


def _view(db: Session, doc: Document) -> dict:
    folder = db.get(Folder, doc.folder_id)
    event = db.get(Event, folder.event_id) if folder.event_id else None
    return {"id": doc.id, "title": doc.title, "category": doc.category, "description": doc.description,
            "status": doc.status, "folder": {"id": folder.id, "name": folder.name},
            "event": {"id": event.id, "name": event.name} if event else None,
            "created_by": _person(db, doc.created_by), "created_at": doc.created_at,
            "current_version": _version_view(db, _current_version(db, doc.id))}


def search(db: Session, user: User, folder_id: int | None, event_id: int | None, q: str | None,
           status: str | None, category: str | None, limit: int) -> list[dict]:
    departments = visible_department_ids(db, user, "documents.view")
    if departments is None:
        visible = true()
    else:
        team = select(EventTeamMember.event_id).where(EventTeamMember.user_id == user.id,
                                                      EventTeamMember.removed_at.is_(None))
        conditions = [Folder.event_id.in_(select(Event.id).where(Event.owner_id == user.id)), Folder.event_id.in_(team)]
        if departments:
            conditions.append(Folder.event_id.in_(select(EventDepartment.event_id)
                                                  .where(EventDepartment.department_id.in_(departments))))
        visible = or_(*conditions)
    stmt = select(Document).join(Folder, Folder.id == Document.folder_id).where(Document.deleted_at.is_(None), visible)
    if folder_id:
        stmt = stmt.where(Document.folder_id == folder_id)
    if event_id:
        stmt = stmt.where(Folder.event_id == event_id)
    if status:
        stmt = stmt.where(Document.status == status)
    if category:
        stmt = stmt.where(Document.category.icontains(category, autoescape=True))
    if q:
        stmt = stmt.where(or_(Document.title.icontains(q, autoescape=True),
                              Document.description.icontains(q, autoescape=True)))
    docs = db.scalars(stmt.order_by(Document.created_at.desc(), Document.id.desc()).limit(limit)).all()
    return [_view(db, d) for d in docs]


def detail(db: Session, user: User, document_id: int) -> dict:
    doc, _, access = _document(db, user, document_id)
    versions = db.scalars(select(DocumentVersion).where(DocumentVersion.document_id == doc.id)
                          .order_by(DocumentVersion.version_no.desc())).all()
    reviews = db.scalars(select(DocumentReview).where(DocumentReview.document_id == doc.id)
                         .order_by(DocumentReview.created_at.desc(), DocumentReview.id.desc())).all()
    return {**_view(db, doc), "versions": [_version_view(db, v) for v in versions],
            "reviews": [{"from_status": r.from_status, "to_status": r.to_status, "remarks": r.remarks,
                         "reviewer": _person(db, r.reviewer_id), "created_at": r.created_at} for r in reviews],
            "allowed_reviews": _allowed_reviews(db, user, doc, access),
            "can_upload_version": access.upload and doc.status not in LOCKED,
            "can_delete": can(db, user, "documents.delete", access.scope)}
