from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.org.schemas import PersonRef


class FolderIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    event_id: int | None = None


class FolderRenameIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class ReviewIn(BaseModel):
    to_status: Literal["submitted", "approved", "rejected", "final", "archived"]
    remarks: str | None = Field(default=None, max_length=2000)


class FolderOut(BaseModel):
    id: int
    name: str
    document_count: int


class FolderListOut(BaseModel):
    folders: list[FolderOut]
    can_upload: bool
    can_manage: bool


class VersionOut(BaseModel):
    id: int
    version_no: int
    original_filename: str
    mime_type: str
    size_bytes: int
    uploaded_by: PersonRef
    uploaded_at: datetime


class Ref(BaseModel):
    id: int
    name: str


class DocumentOut(BaseModel):
    id: int
    title: str
    category: str | None
    description: str | None
    status: str
    folder: Ref
    event: Ref | None
    created_by: PersonRef
    created_at: datetime
    current_version: VersionOut


class ReviewOut(BaseModel):
    from_status: str | None
    to_status: str
    remarks: str | None
    reviewer: PersonRef
    created_at: datetime


class DocumentDetailOut(DocumentOut):
    versions: list[VersionOut]
    reviews: list[ReviewOut]
    allowed_reviews: list[str]
    can_upload_version: bool
    can_delete: bool


class DownloadOut(BaseModel):
    url: str
