from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile
from sqlalchemy.orm import Session

from app.auth.deps import require_in_service
from app.core.db import get_db
from app.core.errors import AppError
from app.documents import service
from app.documents.schemas import (DocumentDetailOut, DocumentOut, DownloadOut, FolderIn, FolderListOut,
                                   FolderRenameIn, ReviewIn)
from app.users.models import User

router = APIRouter(prefix="/api/documents", tags=["documents"])

# An event's owner and team also work in its folders, so routes only require a signed-in user and
# the service checks documents.* at the folder's scope, or that involvement.


def _read(file: UploadFile) -> bytes:
    content = file.file.read(service.MAX_FILE_BYTES + 1)
    if len(content) > service.MAX_FILE_BYTES:
        raise AppError(413, "FILE_TOO_LARGE", f"This file is too large. The limit is {service.MAX_FILE_BYTES // service.MB} MB.")
    return content


@router.get("/folders", response_model=FolderListOut)
def list_folders(event_id: int | None = None, user: User = Depends(require_in_service("documents.view")),
                 db: Session = Depends(get_db)):
    return service.list_folders(db, user, event_id)


@router.post("/folders", status_code=204)
def create_folder(body: FolderIn, user: User = Depends(require_in_service("documents.manage_folders")),
                  db: Session = Depends(get_db)):
    service.create_folder(db, user, body)
    return Response(status_code=204)


@router.put("/folders/{folder_id}", status_code=204)
def rename_folder(folder_id: int, body: FolderRenameIn, user: User = Depends(require_in_service("documents.manage_folders")),
                  db: Session = Depends(get_db)):
    service.rename_folder(db, user, folder_id, body)
    return Response(status_code=204)


@router.delete("/folders/{folder_id}", status_code=204)
def delete_folder(folder_id: int, user: User = Depends(require_in_service("documents.manage_folders")),
                  db: Session = Depends(get_db)):
    service.delete_folder(db, user, folder_id)
    return Response(status_code=204)


@router.get("", response_model=list[DocumentOut])
def search(folder_id: int | None = None, event_id: int | None = None, q: str | None = None, status: str | None = None,
           category: str | None = None, limit: int = Query(default=100, ge=1, le=200),
           user: User = Depends(require_in_service("documents.view")), db: Session = Depends(get_db)):
    return service.search(db, user, folder_id, event_id, q, status, category, limit)


@router.post("", response_model=DocumentDetailOut, status_code=201)
def upload(folder_id: int = Form(), title: str = Form(max_length=200), category: str | None = Form(default=None, max_length=80),
           description: str | None = Form(default=None, max_length=2000), file: UploadFile = File(),
           user: User = Depends(require_in_service("documents.upload")), db: Session = Depends(get_db)):
    doc = service.upload(db, user, folder_id, title, category, description, file.filename or "", _read(file))
    return service.detail(db, user, doc.id)


@router.get("/{document_id}", response_model=DocumentDetailOut)
def get_document(document_id: int, user: User = Depends(require_in_service("documents.view")),
                 db: Session = Depends(get_db)):
    return service.detail(db, user, document_id)


@router.post("/{document_id}/versions", response_model=DocumentDetailOut, status_code=201)
def add_version(document_id: int, file: UploadFile = File(), user: User = Depends(require_in_service("documents.upload")),
                db: Session = Depends(get_db)):
    service.add_version(db, user, document_id, file.filename or "", _read(file))
    return service.detail(db, user, document_id)


@router.post("/{document_id}/review", response_model=DocumentDetailOut)
def review(document_id: int, body: ReviewIn, user: User = Depends(require_in_service("documents.review")),
           db: Session = Depends(get_db)):
    service.review(db, user, document_id, body)
    return service.detail(db, user, document_id)


@router.get("/{document_id}/download", response_model=DownloadOut)
def download(document_id: int, version_id: int | None = None, inline: bool = False,
             user: User = Depends(require_in_service("documents.view")), db: Session = Depends(get_db)):
    return {"url": service.download_url(db, user, document_id, version_id, inline)}


@router.delete("/{document_id}", status_code=204)
def delete_document(document_id: int, user: User = Depends(require_in_service("documents.delete")),
                    db: Session = Depends(get_db)):
    service.soft_delete(db, user, document_id)
    return Response(status_code=204)
