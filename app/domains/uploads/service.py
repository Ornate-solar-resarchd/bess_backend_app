from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import UploadFile

from app.core.config import settings
from app.domains.uploads.schemas import ChecklistPhotoUploadRead, DocumentUploadRead
from app.services.s3 import is_s3_media_enabled, upload_bytes_to_s3
from app.shared.exceptions import APIValidationException

_MAX_CHECKLIST_IMAGE_BYTES = 10 * 1024 * 1024  # 10 MB
_MAX_DOCUMENT_BYTES = 25 * 1024 * 1024  # 25 MB


def _sanitize_filename(raw_name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", raw_name).strip("._")
    return cleaned or "checklist_photo"


def _sanitize_folder(raw_folder: str | None) -> str:
    if raw_folder is None:
        return "documents"
    cleaned = re.sub(r"[^A-Za-z0-9/_-]+", "_", raw_folder).strip("/_")
    if not cleaned:
        return "documents"
    return cleaned


def _filename_from_url(file_url: str) -> str:
    return Path(urlparse(file_url).path).name


async def upload_checklist_photo(file: UploadFile) -> ChecklistPhotoUploadRead:
    if not file.filename:
        raise APIValidationException("file is required")

    content = await file.read()
    if not content:
        raise APIValidationException("Uploaded file is empty")
    if len(content) > _MAX_CHECKLIST_IMAGE_BYTES:
        raise APIValidationException("File size exceeds 10 MB")

    content_type = (file.content_type or "").lower()
    if not content_type.startswith("image/"):
        raise APIValidationException("Only image files are allowed for checklist photo upload")

    extension = Path(file.filename).suffix.lower() or ".jpg"
    safe_basename = _sanitize_filename(Path(file.filename).stem)
    saved_name = f"{safe_basename}_{uuid4().hex}{extension}"

    relative_dir = Path("checklist_photos")
    if is_s3_media_enabled():
        file_url = upload_bytes_to_s3(
            content=content,
            original_filename=file.filename,
            folder=relative_dir.as_posix(),
            content_type=file.content_type,
        )
        saved_name = _filename_from_url(file_url)
    else:
        output_dir = Path(settings.media_root) / relative_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / saved_name
        output_file.write_bytes(content)
        file_url = f"/media/{relative_dir.as_posix()}/{saved_name}"

    return ChecklistPhotoUploadRead(
        file_name=saved_name,
        file_url=file_url,
        content_type=file.content_type,
        size_bytes=len(content),
        uploaded_at=datetime.now(UTC),
    )


async def upload_document(file: UploadFile, folder: str | None = None) -> DocumentUploadRead:
    if not file.filename:
        raise APIValidationException("file is required")

    content = await file.read()
    if not content:
        raise APIValidationException("Uploaded file is empty")
    if len(content) > _MAX_DOCUMENT_BYTES:
        raise APIValidationException("File size exceeds 25 MB")

    extension = Path(file.filename).suffix.lower()
    safe_basename = _sanitize_filename(Path(file.filename).stem or "document")
    saved_name = f"{safe_basename}_{uuid4().hex}{extension}"

    safe_folder = _sanitize_folder(folder)
    relative_dir = Path(safe_folder)
    if is_s3_media_enabled():
        file_url = upload_bytes_to_s3(
            content=content,
            original_filename=file.filename,
            folder=relative_dir.as_posix(),
            content_type=file.content_type,
        )
        saved_name = _filename_from_url(file_url)
    else:
        output_dir = Path(settings.media_root) / relative_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / saved_name
        output_file.write_bytes(content)
        file_url = f"/media/{relative_dir.as_posix()}/{saved_name}"

    return DocumentUploadRead(
        file_name=saved_name,
        file_url=file_url,
        content_type=file.content_type,
        size_bytes=len(content),
        folder=relative_dir.as_posix(),
        uploaded_at=datetime.now(UTC),
    )
