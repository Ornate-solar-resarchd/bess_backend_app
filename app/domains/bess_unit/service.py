from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import qrcode
from fastapi import UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import create_scoped_token, decode_token
from app.domains.auth.models import User
from app.domains.bess_unit.models import AuditLog, BESSUnit, StageCertificate, StageHistory
from app.domains.bess_unit.repository import bess_repository
from app.domains.bess_unit.schemas import (
    BESSShipmentRead,
    BESSUnitCreate,
    BESSUnitRegisterFromQR,
    PaginatedBESSShipments,
    PaginatedStageCertificates,
    StageCertificateCreate,
    StageCertificateRead,
    BESSUnitUpdate,
    ChecklistScanItem,
    QRParseResponse,
    ScanEngineer,
    ScanResponse,
)
from app.domains.engineer.tasks import auto_assign_engineer_task
from app.domains.installation.service import ensure_handover_document
from app.domains.installation.repository import checklist_repository
from app.domains.master.models import City, Country, ProductModel
from app.domains.master.normalization import build_product_description, normalize_hess_to_uess
from app.domains.shipment.repository import shipment_repository
from app.services.s3 import is_s3_media_enabled, upload_bytes_to_s3
from app.shared.acid import atomic
from app.shared.enums import BESSStage, SITE_STAGES, STAGE_TRANSITIONS
from app.shared.exceptions import (
    APIConflictException,
    APIForbiddenException,
    APINotFoundException,
    APIValidationException,
    BESSNotFoundException,
    ChecklistIncompleteException,
    InvalidStageTransitionException,
)


STAGE_INSTRUCTIONS: dict[BESSStage, str] = {
    BESSStage.SITE_ARRIVED: "Inspect delivered unit and validate serial before unloading.",
    BESSStage.CIVIL_INSTALLATION: "Complete civil foundation, leveling, anchoring, and clearances.",
    BESSStage.DC_INSTALLATION: "Perform DC wiring with breaker-off and torque verification steps.",
    BESSStage.AC_INSTALLATION: "Perform AC grid wiring, sequence, voltage and grounding checks.",
    BESSStage.PRE_COMMISSION: "Verify wiring, comm links, safety gear, and warning lockout signage.",
    BESSStage.COLD_COMMISSION: "Power auxiliary systems and verify zero-alarm startup condition.",
    BESSStage.HOT_COMMISSION: "Run charge/discharge and grid sync test with performance logging.",
    BESSStage.FINAL_ACCEPTANCE: "Collect QA and customer signoff with all documentation uploaded.",
    BESSStage.ACTIVE: "Unit is live and operating in production state.",
}

LOGISTICS_CERT_REQUIRED_STAGES = {
    BESSStage.PORT_ARRIVED,
    BESSStage.PORT_CLEARED,
    BESSStage.WAREHOUSE_STORED,
}

SERIAL_KEYS = (
    "serial_number",
    "serial",
    "factory_code",
    "factory_sn",
    "sn",
)
MODEL_KEYS = (
    "model_number",
    "product_model",
    "model",
)
MANUFACTURED_DATE_KEYS = (
    "manufactured_date",
    "manufacture_date",
    "manufacturing_date",
    "made_date",
    "mfg_date",
)


@dataclass(slots=True)
class ParsedQRPayload:
    serial_number: str | None
    model_number: str | None
    manufactured_date: datetime | None
    normalized_fields: dict[str, str]


def _mask_phone(phone: str | None) -> str | None:
    if phone is None or len(phone) < 4:
        return phone
    return f"{'*' * max(0, len(phone) - 4)}{phone[-4:]}"


def _build_scan_url(serial_number: str) -> str:
    if settings.qr_code_base_url.rstrip("/").endswith("/api/v1/bess/scan"):
        return f"{settings.qr_code_base_url.rstrip('/')}/{serial_number}"
    return f"{settings.qr_code_base_url.rstrip('/')}/api/v1/bess/scan/{serial_number}"


def _build_public_scan_url(bess_unit_id: int) -> str:
    token = create_scoped_token(
        subject={"scope": "bess_public_scan", "bess_unit_id": bess_unit_id},
        expires_delta=timedelta(days=30),
        token_type="bess_public_scan",
    )
    return f"{settings.qr_code_base_url.rstrip('/')}{settings.api_v1_prefix}/bess/{bess_unit_id}/public-scan?token={token}"


def _is_bess_profile_complete(unit: BESSUnit) -> bool:
    return bool(
        unit.site_address
        and unit.site_latitude is not None
        and unit.site_longitude is not None
        and unit.customer_user_id is not None
    )


def _ensure_qr_file(serial_number: str, encoded_url: str | None = None) -> tuple[str, Path]:
    media_root = Path(settings.media_root)
    qr_dir = media_root / "qr"
    qr_dir.mkdir(parents=True, exist_ok=True)

    file_name = f"{serial_number}.png"
    file_path = qr_dir / file_name
    public_url = f"/media/qr/{file_name}"

    qr_data = encoded_url or _build_scan_url(serial_number)

    img = qrcode.make(qr_data)
    img.save(file_path)
    return public_url, file_path


def _resolve_qr_target_for_unit(unit: BESSUnit) -> str:
    if _is_bess_profile_complete(unit):
        return _build_public_scan_url(unit.id)
    return _build_scan_url(unit.serial_number)


def _build_bess_qr_payload(unit: BESSUnit, model: ProductModel | None) -> dict[str, object]:
    payload: dict[str, object] = {
        "document_type": "BESS_UNIT_QR",
        "version": "1.0",
        "bess_unit_id": unit.id,
        "serial_number": unit.serial_number,
        "model_number": model.model_number if model else None,
        "model_capacity_kwh": model.capacity_kwh if model else None,
        "current_stage": unit.current_stage.value,
        "scan_url": _build_scan_url(unit.serial_number),
        "public_scan_url": _resolve_qr_target_for_unit(unit),
    }
    if unit.manufactured_date is not None:
        payload["manufactured_date"] = unit.manufactured_date.isoformat()
    return payload


def _encode_qr_payload(payload: dict[str, object]) -> str:
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=True, sort_keys=True)


def _save_uploaded_nameplate_photo(photo: UploadFile, content: bytes) -> str:
    ext = Path(photo.filename or "").suffix.lower()
    if ext not in {".jpg", ".jpeg", ".png", ".webp", ".bmp"}:
        ext = ".jpg"

    if is_s3_media_enabled():
        return upload_bytes_to_s3(
            content=content,
            original_filename=f"nameplate{ext}",
            folder="nameplates",
            content_type=photo.content_type,
        )

    media_root = Path(settings.media_root)
    photo_dir = media_root / "nameplates"
    photo_dir.mkdir(parents=True, exist_ok=True)

    file_name = f"{uuid.uuid4().hex}{ext}"
    file_path = photo_dir / file_name
    file_path.write_bytes(content)
    return f"/media/nameplates/{file_name}"


def _extract_text_from_nameplate_photo(photo_url: str, content: bytes | None = None) -> str:
    try:
        import pytesseract
        from PIL import Image
    except ImportError as exc:
        raise APIValidationException(
            "OCR dependency missing. Install pytesseract and Tesseract OCR binary, or send ocr_text_override."
        ) from exc

    try:
        if content is not None:
            image = Image.open(BytesIO(content))
        else:
            relative = photo_url.replace("/media/", "", 1)
            file_path = Path(settings.media_root) / relative
            if not file_path.exists():
                raise APIValidationException("Uploaded photo not found for OCR processing.")
            image = Image.open(file_path)
        text = pytesseract.image_to_string(image)
    except Exception as exc:  # pragma: no cover - defensive runtime guard
        raise APIValidationException("Failed to extract text from uploaded photo.") from exc

    cleaned = text.strip()
    if not cleaned:
        raise APIValidationException("OCR found no readable text. Try clearer photo or ocr_text_override.")
    return cleaned


def _normalize_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", key.strip().lower()).strip("_")


def _parse_manufactured_date(value: str | None) -> datetime | None:
    if not value:
        return None
    raw = value.strip()
    if not raw:
        return None

    sanitized = (
        raw.replace("年", "-")
        .replace("月", "-")
        .replace("日", "")
        .replace("/", "-")
        .replace(".", "-")
    )
    sanitized = re.sub(r"-+", "-", sanitized).strip("-")

    for pattern in ("%Y-%m-%d", "%Y-%m", "%Y"):
        try:
            parsed = datetime.strptime(sanitized, pattern)
            if pattern == "%Y":
                parsed = parsed.replace(month=1, day=1)
            elif pattern == "%Y-%m":
                parsed = parsed.replace(day=1)
            return parsed.replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def _collect_fields(normalized_fields: dict[str, str], source: dict[str, object]) -> None:
    for key, value in source.items():
        normalized_key = _normalize_key(str(key))
        if not normalized_key:
            continue
        if isinstance(value, dict):
            for nested_key, nested_value in value.items():
                nested = _normalize_key(str(nested_key))
                if nested and nested_value is not None:
                    normalized_fields.setdefault(nested, normalize_hess_to_uess(str(nested_value).strip()))
            continue
        if value is None:
            continue
        normalized_fields.setdefault(normalized_key, normalize_hess_to_uess(str(value).strip()))


def _extract_url_fields(normalized_fields: dict[str, str], raw_data: str) -> str | None:
    try:
        parsed = urlparse(raw_data.strip())
    except ValueError:
        return None
    if not parsed.scheme or not parsed.netloc:
        return None

    for key, values in parse_qs(parsed.query).items():
        if values:
            normalized_fields.setdefault(_normalize_key(key), normalize_hess_to_uess(values[0].strip()))

    path_segments = [segment for segment in parsed.path.split("/") if segment]
    if not path_segments:
        return None
    candidate = path_segments[-1].strip()
    if candidate and candidate.lower() not in {"scan", "bess", "api", "v1"}:
        return candidate
    return None


def _extract_key_value_fields(normalized_fields: dict[str, str], raw_data: str) -> None:
    for token in re.split(r"[\n;,|]+", raw_data):
        part = token.strip()
        if not part:
            continue
        if ":" in part:
            key, value = part.split(":", 1)
        elif "=" in part:
            key, value = part.split("=", 1)
        else:
            continue
        normalized_key = _normalize_key(key)
        if normalized_key and value.strip():
            normalized_fields.setdefault(normalized_key, normalize_hess_to_uess(value.strip()))


def _parse_qr_payload(raw_data: str) -> ParsedQRPayload:
    raw = raw_data.strip()
    if not raw:
        raise APIValidationException("qr_raw_data cannot be empty")

    normalized_fields: dict[str, str] = {}
    serial_from_url = _extract_url_fields(normalized_fields, raw)

    try:
        json_payload = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        json_payload = None
    if isinstance(json_payload, dict):
        _collect_fields(normalized_fields, json_payload)

    _extract_key_value_fields(normalized_fields, raw)

    serial_number: str | None = None
    for key in SERIAL_KEYS:
        value = normalized_fields.get(key)
        if value:
            serial_number = value
            break
    if not serial_number and serial_from_url:
        serial_number = serial_from_url
    if not serial_number and re.fullmatch(r"[A-Za-z0-9._:-]{6,}", raw):
        serial_number = raw

    model_number: str | None = None
    for key in MODEL_KEYS:
        value = normalized_fields.get(key)
        if value:
            model_number = normalize_hess_to_uess(value)
            break

    manufactured_date: datetime | None = None
    for key in MANUFACTURED_DATE_KEYS:
        manufactured_date = _parse_manufactured_date(normalized_fields.get(key))
        if manufactured_date:
            break

    return ParsedQRPayload(
        serial_number=serial_number.strip().upper() if serial_number else None,
        model_number=model_number.strip().upper() if model_number else None,
        manufactured_date=manufactured_date,
        normalized_fields=normalized_fields,
    )


async def parse_qr_data(raw_data: str) -> QRParseResponse:
    parsed = _parse_qr_payload(raw_data)
    can_register = parsed.serial_number is not None
    message = (
        "QR parsed successfully; serial detected."
        if can_register
        else "Serial number not detected in QR payload; use serial_number_override."
    )
    return QRParseResponse(
        serial_number=parsed.serial_number,
        model_number=parsed.model_number,
        manufactured_date=parsed.manufactured_date,
        normalized_fields=parsed.normalized_fields,
        can_register=can_register,
        message=message,
    )


async def _resolve_product_model_id(
    db: AsyncSession,
    provided_product_model_id: int | None,
    parsed_model_number: str | None,
    parsed_fields: dict[str, str] | None = None,
) -> int:
    def _extract_capacity_kwh(fields: dict[str, str] | None) -> float | None:
        if not fields:
            return None

        prioritized_keys = (
            "capacity_kwh",
            "system_rated_energy",
            "rated_energy",
            "product_name",
        )
        values: list[str] = []
        for key in prioritized_keys:
            value = fields.get(key)
            if value:
                values.append(value)
        values.extend(v for v in fields.values() if v)

        for raw in values:
            text = str(raw)
            match = re.search(r"(\d+(?:\.\d+)?)\s*kwh", text, flags=re.IGNORECASE)
            if match:
                return float(match.group(1))
            if "capacity_kwh" in text.lower() or "rated_energy" in text.lower():
                number = re.search(r"(\d+(?:\.\d+)?)", text)
                if number:
                    return float(number.group(1))
        return None

    if provided_product_model_id is not None:
        product_model = await db.get(ProductModel, provided_product_model_id)
        if not product_model:
            raise APINotFoundException("Product model not found")
        return product_model.id

    if parsed_model_number:
        normalized_model = normalize_hess_to_uess(parsed_model_number)
        legacy_model = normalized_model.replace("UESS", "HESS", 1)
        stmt = select(ProductModel).where(
            (func.lower(ProductModel.model_number) == normalized_model.lower())
            | (func.lower(ProductModel.model_number) == legacy_model.lower())
        )
        model = await db.scalar(stmt)
        if model is not None:
            if model.model_number != normalized_model:
                model.model_number = normalized_model
                await db.flush()
            return model.id

        capacity_kwh = _extract_capacity_kwh(parsed_fields)
        if capacity_kwh is None:
            raise APIValidationException(
                "Unable to auto-create product model because capacity_kwh was not found in QR/photo data. "
                "Provide product_model_id."
            )

        description = build_product_description(None, parsed_fields)
        created_model = ProductModel(
            model_number=normalized_model,
            capacity_kwh=capacity_kwh,
            description=description,
        )
        db.add(created_model)
        await db.flush()
        return created_model.id

    raise APIValidationException(
        "Unable to resolve product model from QR/photo data. Provide product_model_id in request."
    )


async def register_bess_from_qr(
    db: AsyncSession,
    payload: BESSUnitRegisterFromQR,
    current_user: User,
) -> BESSUnit:
    parsed = _parse_qr_payload(payload.qr_raw_data)
    serial_number = payload.serial_number_override.strip().upper() if payload.serial_number_override else parsed.serial_number
    if not serial_number:
        raise APIValidationException("Serial number not found in QR payload. Provide serial_number_override.")

    product_model_id = await _resolve_product_model_id(
        db,
        payload.product_model_id,
        parsed.model_number,
        parsed.normalized_fields,
    )
    manufactured_date = payload.manufactured_date or parsed.manufactured_date

    if payload.warehouse_id is not None:
        raise APIValidationException(
            "warehouse_id must be empty at factory registration. Set warehouse later when unit arrives."
        )

    return await create_bess_unit(
        db,
        BESSUnitCreate(
            serial_number=serial_number,
            existing_qr_code_url=payload.existing_qr_code_url,
            nameplate_photo_url=None,
            regenerate_qr_png=False,
            product_model_id=product_model_id,
            country_id=payload.country_id,
            city_id=payload.city_id,
            warehouse_id=None,
            site_address=payload.site_address,
            site_latitude=payload.site_latitude,
            site_longitude=payload.site_longitude,
            customer_user_id=payload.customer_user_id,
            manufactured_date=manufactured_date,
        ),
        current_user,
    )


async def register_bess_from_photo(
    db: AsyncSession,
    *,
    photo: UploadFile,
    country_id: int,
    city_id: int,
    current_user: User,
    ocr_text_override: str | None = None,
    serial_number_override: str | None = None,
    existing_qr_code_url: str | None = None,
    product_model_id: int | None = None,
    site_address: str | None = None,
    site_latitude: float | None = None,
    site_longitude: float | None = None,
    customer_user_id: int | None = None,
    manufactured_date: datetime | None = None,
) -> BESSUnit:
    if not photo.filename:
        raise APIValidationException("photo file is required")

    content = await photo.read()
    if not content:
        raise APIValidationException("Uploaded photo is empty")

    photo_url = _save_uploaded_nameplate_photo(photo, content)
    parsed_text = (
        ocr_text_override.strip()
        if ocr_text_override
        else _extract_text_from_nameplate_photo(photo_url, content)
    )
    parsed = _parse_qr_payload(parsed_text)

    serial_number = serial_number_override.strip().upper() if serial_number_override else parsed.serial_number
    if not serial_number:
        raise APIValidationException("Serial number not found from photo OCR. Provide serial_number_override.")

    resolved_product_model_id = await _resolve_product_model_id(
        db,
        product_model_id,
        parsed.model_number,
        parsed.normalized_fields,
    )
    resolved_manufactured_date = manufactured_date or parsed.manufactured_date

    return await create_bess_unit(
        db,
        BESSUnitCreate(
            serial_number=serial_number,
            existing_qr_code_url=existing_qr_code_url,
            nameplate_photo_url=photo_url,
            regenerate_qr_png=True,
            product_model_id=resolved_product_model_id,
            country_id=country_id,
            city_id=city_id,
            warehouse_id=None,
            site_address=site_address,
            site_latitude=site_latitude,
            site_longitude=site_longitude,
            customer_user_id=customer_user_id,
            manufactured_date=resolved_manufactured_date,
        ),
        current_user,
    )


async def create_bess_unit(db: AsyncSession, payload: BESSUnitCreate, current_user: User) -> BESSUnit:
    product_model = await db.get(ProductModel, payload.product_model_id)
    if not product_model:
        raise APINotFoundException("Product model not found")
    country = await db.get(Country, payload.country_id)
    if not country:
        raise APINotFoundException("Country not found")
    city = await db.get(City, payload.city_id)
    if not city:
        raise APINotFoundException("City not found")

    serial_number = payload.serial_number.strip().upper() if payload.serial_number else f"BESS-{uuid.uuid4().hex[:12].upper()}"
    existing = await bess_repository.get_by_serial(db, serial_number)
    if existing is not None:
        raise APIConflictException(f"BESS unit with serial '{serial_number}' already exists")

    qr_code_url: str | None = payload.existing_qr_code_url

    async with atomic(db) as session:
        unit = BESSUnit(
            serial_number=serial_number,
            qr_code_url=qr_code_url,
            nameplate_photo_url=payload.nameplate_photo_url,
            product_model_id=payload.product_model_id,
            country_id=payload.country_id,
            city_id=payload.city_id,
            warehouse_id=payload.warehouse_id,
            site_address=payload.site_address,
            site_latitude=payload.site_latitude,
            site_longitude=payload.site_longitude,
            customer_user_id=payload.customer_user_id,
            manufactured_date=payload.manufactured_date,
            current_stage=BESSStage.FACTORY_REGISTERED,
            is_active=False,
        )
        unit = await bess_repository.create(session, unit)
        if payload.regenerate_qr_png:
            qr_payload = _build_bess_qr_payload(unit, product_model)
            qr_code_url, _ = _ensure_qr_file(serial_number, _encode_qr_payload(qr_payload))
            unit.qr_code_url = qr_code_url
            await session.flush()

        await bess_repository.create_audit_log(
            session,
            AuditLog(
                user_id=current_user.id,
                action="BESS_CREATE",
                entity_type="BESSUnit",
                entity_id=unit.id,
                payload_json={"serial_number": serial_number},
            ),
        )
    return unit


async def update_bess_unit(
    db: AsyncSession,
    bess_unit_id: int,
    payload: BESSUnitUpdate,
    current_user: User,
) -> BESSUnit:
    unit = await bess_repository.get_by_id(db, bess_unit_id)
    if unit is None or unit.is_deleted:
        raise BESSNotFoundException(bess_unit_id)

    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        return unit

    async with atomic(db) as session:
        for key, value in changes.items():
            setattr(unit, key, value)
        model = await session.get(ProductModel, unit.product_model_id)
        qr_payload = _build_bess_qr_payload(unit, model)
        qr_code_url, _ = _ensure_qr_file(unit.serial_number, _encode_qr_payload(qr_payload))
        unit.qr_code_url = qr_code_url
        unit.updated_at = datetime.now(UTC)
        await session.flush()
        await bess_repository.create_audit_log(
            session,
            AuditLog(
                user_id=current_user.id,
                action="BESS_UPDATE",
                entity_type="BESSUnit",
                entity_id=unit.id,
                payload_json=changes,
            ),
        )
    return unit


async def get_bess_unit(db: AsyncSession, bess_unit_id: int) -> BESSUnit:
    unit = await bess_repository.get_by_id(db, bess_unit_id)
    if unit is None or unit.is_deleted:
        raise BESSNotFoundException(bess_unit_id)
    return unit


async def list_bess_units(
    db: AsyncSession,
    page: int,
    size: int,
    city_id: int | None,
    country_id: int | None,
    stage: BESSStage | None,
    serial: str | None,
    customer_user_id: int | None,
):
    return await bess_repository.list_units(
        db,
        page=page,
        size=size,
        city_id=city_id,
        country_id=country_id,
        stage=stage,
        serial=serial,
        customer_user_id=customer_user_id,
    )


async def list_bess_shipments(
    db: AsyncSession,
    bess_unit_id: int,
    page: int,
    size: int,
    customer_user_id: int | None,
) -> PaginatedBESSShipments:
    unit = await bess_repository.get_by_id(db, bess_unit_id)
    if unit is None or unit.is_deleted:
        raise BESSNotFoundException(bess_unit_id)
    if customer_user_id is not None and unit.customer_user_id != customer_user_id:
        raise APIForbiddenException("You are not allowed to view shipments for this BESS unit")

    total, links = await shipment_repository.list_shipments_for_bess(db, bess_unit_id, page, size)
    items = [
        BESSShipmentRead(
            shipment_id=link.shipment_id,
            shipment_code=link.shipment.shipment_code,
            shipment_status=link.shipment.status,
            order_id=link.order_id,
            linked_at=link.created_at,
        )
        for link in links
    ]
    return PaginatedBESSShipments(total=total, items=items, page=page, size=size)


async def transition_stage(
    bess_unit_id: int,
    to_stage: BESSStage,
    notes: str | None,
    current_user: User,
    db: AsyncSession,
) -> BESSUnit:
    unit = await bess_repository.get_by_id(db, bess_unit_id)
    if unit is None or unit.is_deleted:
        raise BESSNotFoundException(bess_unit_id)

    from_stage = unit.current_stage
    allowed_next = STAGE_TRANSITIONS.get(from_stage)
    if allowed_next != to_stage:
        raise InvalidStageTransitionException(from_stage, to_stage)

    if from_stage in LOGISTICS_CERT_REQUIRED_STAGES:
        cert_count = await bess_repository.count_stage_certificates(db, bess_unit_id, from_stage)
        if cert_count < 1:
            raise APIValidationException(
                f"Certificate is required for stage '{from_stage.value}' before moving to '{to_stage.value}'."
            )

    if to_stage == BESSStage.WAREHOUSE_STORED and unit.warehouse_id is None:
        raise APIValidationException("Set warehouse_id via PATCH /api/v1/bess/{id} before WAREHOUSE_STORED stage.")
    if to_stage == BESSStage.DISPATCHED_TO_SITE and not unit.site_address:
        raise APIValidationException("Set site details before DISPATCHED_TO_SITE stage.")

    pending = await checklist_repository.get_incomplete_mandatory(db, bess_unit_id, unit.current_stage)
    if pending:
        raise ChecklistIncompleteException(pending)

    handover_report_url: str | None = None
    if to_stage == BESSStage.ACTIVE:
        handover_report_url = await ensure_handover_document(db, bess_unit_id)

    async with atomic(db, serializable=True) as session:
        unit.current_stage = to_stage
        if to_stage == BESSStage.ACTIVE:
            unit.is_active = True
        model = await session.get(ProductModel, unit.product_model_id)
        qr_payload = _build_bess_qr_payload(unit, model)
        qr_code_url, _ = _ensure_qr_file(unit.serial_number, _encode_qr_payload(qr_payload))
        unit.qr_code_url = qr_code_url
        await session.flush()

        await bess_repository.create_stage_history(
            session,
            StageHistory(
                bess_unit_id=bess_unit_id,
                from_stage=from_stage,
                to_stage=to_stage,
                changed_by_user_id=current_user.id,
                notes=notes,
            ),
        )

        await bess_repository.create_audit_log(
            session,
            AuditLog(
                user_id=current_user.id,
                action="STAGE_TRANSITION",
                entity_type="BESSUnit",
                entity_id=bess_unit_id,
                payload_json={"from": from_stage.value, "to": to_stage.value, "notes": notes},
            ),
        )

        if handover_report_url:
            cert = await bess_repository.create_stage_certificate(
                session,
                StageCertificate(
                    bess_unit_id=bess_unit_id,
                    stage=BESSStage.FINAL_ACCEPTANCE,
                    certificate_name="AUTO_HANDOVER_DOCUMENT",
                    certificate_url=handover_report_url,
                    notes="Auto-generated after final acceptance completion.",
                    uploaded_by_user_id=current_user.id,
                ),
            )
            await bess_repository.create_audit_log(
                session,
                AuditLog(
                    user_id=current_user.id,
                    action="STAGE_CERTIFICATE_ADD",
                    entity_type="StageCertificate",
                    entity_id=cert.id,
                    payload_json={
                        "bess_unit_id": bess_unit_id,
                        "stage": BESSStage.FINAL_ACCEPTANCE.value,
                        "certificate_name": "AUTO_HANDOVER_DOCUMENT",
                    },
                ),
            )

    if to_stage in SITE_STAGES:
        auto_assign_engineer_task.delay(bess_unit_id, to_stage.value)

    return unit


async def add_stage_certificate(
    db: AsyncSession,
    bess_unit_id: int,
    payload: StageCertificateCreate,
    current_user: User,
) -> StageCertificate:
    unit = await bess_repository.get_by_id(db, bess_unit_id)
    if unit is None or unit.is_deleted:
        raise BESSNotFoundException(bess_unit_id)

    async with atomic(db) as session:
        cert = await bess_repository.create_stage_certificate(
            session,
            StageCertificate(
                bess_unit_id=bess_unit_id,
                stage=payload.stage,
                certificate_name=payload.certificate_name.strip(),
                certificate_url=payload.certificate_url.strip(),
                notes=payload.notes,
                uploaded_by_user_id=current_user.id,
            ),
        )
        await bess_repository.create_audit_log(
            session,
            AuditLog(
                user_id=current_user.id,
                action="STAGE_CERTIFICATE_ADD",
                entity_type="StageCertificate",
                entity_id=cert.id,
                payload_json={
                    "bess_unit_id": bess_unit_id,
                    "stage": payload.stage.value,
                    "certificate_name": payload.certificate_name,
                },
            ),
        )
    return cert


async def list_stage_certificates(
    db: AsyncSession,
    bess_unit_id: int,
    stage: BESSStage | None,
    page: int,
    size: int,
) -> PaginatedStageCertificates:
    unit = await bess_repository.get_by_id(db, bess_unit_id)
    if unit is None or unit.is_deleted:
        raise BESSNotFoundException(bess_unit_id)
    total, items = await bess_repository.list_stage_certificates(db, bess_unit_id, stage, page, size)
    return PaginatedStageCertificates(
        total=total,
        items=[StageCertificateRead.model_validate(item) for item in items],
        page=page,
        size=size,
    )


async def list_stage_history(db: AsyncSession, bess_unit_id: int) -> list[StageHistory]:
    unit = await bess_repository.get_by_id(db, bess_unit_id)
    if unit is None or unit.is_deleted:
        raise BESSNotFoundException(bess_unit_id)
    return await bess_repository.list_history(db, bess_unit_id)


async def get_qr_code_file(db: AsyncSession, bess_unit_id: int) -> FileResponse:
    unit = await get_bess_unit(db, bess_unit_id)
    if not unit.qr_code_url:
        raise APINotFoundException("QR code not generated")
    file_path = Path(settings.media_root) / "qr" / f"{unit.serial_number}.png"
    if not file_path.exists():
        raise APINotFoundException("QR image file not found")
    return FileResponse(path=file_path, media_type="image/png", filename=file_path.name)


async def scan_by_serial(db: AsyncSession, serial_number: str) -> ScanResponse:
    unit = await bess_repository.get_by_serial(db, serial_number)
    if unit is None:
        raise APINotFoundException("BESS unit not found")

    return await _build_scan_response(db, unit)


async def _build_scan_response(db: AsyncSession, unit: BESSUnit) -> ScanResponse:
    assigned_engineer = await checklist_repository.get_current_stage_engineer(db, unit.id, unit.current_stage)
    checklist = await checklist_repository.get_stage_checklist(db, unit.id, unit.current_stage)

    return ScanResponse(
        bess_unit=unit,
        product_specs=unit.product_model,
        current_stage=unit.current_stage,
        assigned_engineer=(
            ScanEngineer(name=assigned_engineer.user.full_name, phone_masked=_mask_phone(assigned_engineer.user.phone))
            if assigned_engineer
            else None
        ),
        checklist=[
            ChecklistScanItem(
                item_text=item.item_text,
                is_mandatory=item.is_mandatory,
                is_checked=item.is_checked,
                requires_photo=item.requires_photo,
            )
            for item in checklist
        ],
        stage_instructions=STAGE_INSTRUCTIONS.get(unit.current_stage, "Follow standard operating procedure for this stage."),
    )


async def get_public_scan_by_token(
    db: AsyncSession,
    bess_unit_id: int,
    token: str,
) -> ScanResponse:
    try:
        payload = decode_token(token)
    except ValueError as exc:
        raise APIValidationException("Invalid BESS public scan token") from exc

    if payload.get("type") != "bess_public_scan" or payload.get("scope") != "bess_public_scan":
        raise APIValidationException("Invalid BESS public scan token")

    token_bess_unit_id = payload.get("bess_unit_id")
    if token_bess_unit_id is None or int(token_bess_unit_id) != bess_unit_id:
        raise APIValidationException("Invalid BESS public scan token")

    unit = await bess_repository.get_by_id(db, bess_unit_id)
    if unit is None or unit.is_deleted:
        raise BESSNotFoundException(bess_unit_id)
    return await _build_scan_response(db, unit)
