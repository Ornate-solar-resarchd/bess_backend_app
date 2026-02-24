from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, UploadFile, status

from app.core.dependencies import get_current_user, require_permission
from app.domains.auth.models import User
from app.domains.uploads.schemas import ChecklistPhotoUploadRead, DocumentUploadRead
from app.domains.uploads.service import upload_checklist_photo, upload_document

router = APIRouter(prefix="/uploads", tags=["Uploads"])


@router.post("/checklist-photo", response_model=ChecklistPhotoUploadRead, status_code=status.HTTP_201_CREATED)
async def upload_checklist_photo_endpoint(
    file: UploadFile = File(...),
    _: User = Depends(require_permission("checklist:write")),
) -> ChecklistPhotoUploadRead:
    return await upload_checklist_photo(file)


@router.post("/document", response_model=DocumentUploadRead, status_code=status.HTTP_201_CREATED)
async def upload_document_endpoint(
    file: UploadFile = File(...),
    folder: str | None = Form(default=None),
    _: User = Depends(get_current_user),
) -> DocumentUploadRead:
    return await upload_document(file, folder)
