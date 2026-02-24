from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class ChecklistPhotoUploadRead(BaseModel):
    file_name: str
    file_url: str
    content_type: str | None
    size_bytes: int
    uploaded_at: datetime


class DocumentUploadRead(BaseModel):
    file_name: str
    file_url: str
    content_type: str | None
    size_bytes: int
    folder: str
    uploaded_at: datetime
