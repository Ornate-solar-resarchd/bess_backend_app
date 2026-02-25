from __future__ import annotations

from io import BytesIO
from unittest.mock import Mock

import pytest
from starlette.datastructures import UploadFile

from app.core.config import settings
from app.domains.uploads import service as uploads_service
from app.shared.exceptions import APIValidationException


@pytest.mark.asyncio
async def test_upload_checklist_photo_saves_file_and_returns_media_url(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(settings, "media_root", str(tmp_path))

    file = UploadFile(
        filename="site_photo.jpg",
        file=BytesIO(b"fake-image-bytes"),
        headers={"content-type": "image/jpeg"},
    )

    result = await uploads_service.upload_checklist_photo(file)

    assert result.file_url.startswith("/media/checklist_photos/")
    assert result.size_bytes == len(b"fake-image-bytes")

    output_path = tmp_path / result.file_url.replace("/media/", "")
    assert output_path.exists()
    assert output_path.read_bytes() == b"fake-image-bytes"


@pytest.mark.asyncio
async def test_upload_checklist_photo_rejects_non_image(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(settings, "media_root", str(tmp_path))

    file = UploadFile(
        filename="doc.pdf",
        file=BytesIO(b"%PDF-1.4"),
        headers={"content-type": "application/pdf"},
    )

    with pytest.raises(APIValidationException):
        await uploads_service.upload_checklist_photo(file)


@pytest.mark.asyncio
async def test_upload_document_saves_pdf_and_returns_media_url(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(settings, "media_root", str(tmp_path))

    file = UploadFile(
        filename="port_clearance.pdf",
        file=BytesIO(b"%PDF-1.4 fake"),
        headers={"content-type": "application/pdf"},
    )

    result = await uploads_service.upload_document(file, folder="certificates/port")

    assert result.file_url.startswith("/media/certificates/port/")
    assert result.folder == "certificates/port"
    output_path = tmp_path / result.file_url.replace("/media/", "")
    assert output_path.exists()
    assert output_path.read_bytes() == b"%PDF-1.4 fake"


@pytest.mark.asyncio
async def test_upload_document_rejects_empty_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(settings, "media_root", str(tmp_path))

    file = UploadFile(
        filename="empty.txt",
        file=BytesIO(b""),
        headers={"content-type": "text/plain"},
    )

    with pytest.raises(APIValidationException):
        await uploads_service.upload_document(file, folder="misc")


@pytest.mark.asyncio
async def test_upload_checklist_photo_uses_s3_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "media_storage_backend", "s3")
    monkeypatch.setattr(settings, "aws_s3_bucket", "bess-bucket")
    monkeypatch.setattr(
        uploads_service,
        "upload_bytes_to_s3",
        Mock(return_value="https://cdn.example.com/checklist_photos/abc123.jpg"),
    )

    file = UploadFile(
        filename="site_photo.jpg",
        file=BytesIO(b"fake-image-bytes"),
        headers={"content-type": "image/jpeg"},
    )

    result = await uploads_service.upload_checklist_photo(file)

    assert result.file_url == "https://cdn.example.com/checklist_photos/abc123.jpg"
    assert result.file_name == "abc123.jpg"


@pytest.mark.asyncio
async def test_upload_document_uses_s3_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "media_storage_backend", "s3")
    monkeypatch.setattr(settings, "aws_s3_bucket", "bess-bucket")
    monkeypatch.setattr(
        uploads_service,
        "upload_bytes_to_s3",
        Mock(return_value="https://cdn.example.com/certificates/port/doc001.pdf"),
    )

    file = UploadFile(
        filename="port_clearance.pdf",
        file=BytesIO(b"%PDF-1.4 fake"),
        headers={"content-type": "application/pdf"},
    )

    result = await uploads_service.upload_document(file, folder="certificates/port")

    assert result.file_url == "https://cdn.example.com/certificates/port/doc001.pdf"
    assert result.file_name == "doc001.pdf"
    assert result.folder == "certificates/port"
