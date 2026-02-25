from __future__ import annotations

import os
import re
from functools import lru_cache
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import UploadFile

from app.core.config import settings

try:  # pragma: no cover - exercised in environments with boto3 installed
    import boto3
    from botocore.exceptions import BotoCoreError, ClientError
except ModuleNotFoundError:  # pragma: no cover - local fallback when S3 extras are not installed yet
    boto3 = None  # type: ignore[assignment]

    class BotoCoreError(Exception):
        pass

    class ClientError(Exception):
        pass


def is_s3_media_enabled() -> bool:
    return settings.media_storage_backend == "s3" and bool(settings.aws_s3_bucket)


@lru_cache(maxsize=1)
def _get_s3_client():
    if boto3 is None:
        raise RuntimeError("boto3 is not installed. Install dependencies from requirements.txt.")
    if not settings.aws_s3_bucket:
        raise RuntimeError("AWS_S3_BUCKET is required when MEDIA_STORAGE_BACKEND=s3")

    kwargs: dict[str, str] = {"region_name": settings.aws_region}
    if settings.aws_access_key_id and settings.aws_secret_access_key:
        kwargs["aws_access_key_id"] = settings.aws_access_key_id
        kwargs["aws_secret_access_key"] = settings.aws_secret_access_key
    return boto3.client("s3", **kwargs)


def _sanitize_folder(raw_folder: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9/_-]+", "_", raw_folder).strip("/_")
    return cleaned or "uploads"


def _get_base_url() -> str:
    if settings.aws_s3_base_url:
        return settings.aws_s3_base_url.rstrip("/")
    return f"https://{settings.aws_s3_bucket}.s3.{settings.aws_region}.amazonaws.com"


def _build_key(original_filename: str | None, folder: str) -> str:
    ext = os.path.splitext(original_filename or "")[1].lower()
    safe_folder = _sanitize_folder(folder)
    return f"{safe_folder}/{uuid4().hex}{ext}"


def upload_bytes_to_s3(
    *,
    content: bytes,
    original_filename: str | None,
    folder: str = "uploads",
    content_type: str | None = None,
) -> str:
    if not is_s3_media_enabled():
        raise RuntimeError("S3 media storage is not enabled")

    key = _build_key(original_filename, folder)
    put_args: dict[str, object] = {
        "Bucket": settings.aws_s3_bucket,
        "Key": key,
        "Body": content,
    }
    if content_type:
        put_args["ContentType"] = content_type

    try:
        _get_s3_client().put_object(**put_args)
        return f"{_get_base_url()}/{key}"
    except (ClientError, BotoCoreError) as exc:
        raise RuntimeError(f"S3 upload failed: {exc}") from exc


async def upload_file_to_s3(file: UploadFile, folder: str = "uploads") -> str:
    content = await file.read()
    return upload_bytes_to_s3(
        content=content,
        original_filename=file.filename,
        folder=folder,
        content_type=file.content_type,
    )


def _extract_key_from_url(file_url: str) -> str:
    base_url = _get_base_url()
    if file_url.startswith(f"{base_url}/"):
        return file_url.replace(f"{base_url}/", "", 1)

    parsed = urlparse(file_url)
    return parsed.path.lstrip("/")


async def delete_file_from_s3(file_url: str) -> bool:
    if not is_s3_media_enabled():
        raise RuntimeError("S3 media storage is not enabled")

    key = _extract_key_from_url(file_url)
    try:
        _get_s3_client().delete_object(Bucket=settings.aws_s3_bucket, Key=key)
        return True
    except (ClientError, BotoCoreError) as exc:
        raise RuntimeError(f"S3 delete failed: {exc}") from exc
