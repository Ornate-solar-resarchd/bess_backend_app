from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

import qrcode
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.domains.auth.models import User
from app.domains.bess_unit.models import AuditLog, BESSUnit, StageHistory
from app.domains.bess_unit.repository import bess_repository
from app.domains.bess_unit.schemas import BESSUnitCreate, BESSUnitUpdate, ChecklistScanItem, ScanEngineer, ScanResponse
from app.domains.engineer.tasks import auto_assign_engineer_task
from app.domains.installation.repository import checklist_repository
from app.domains.master.models import City, Country, ProductModel
from app.shared.acid import atomic
from app.shared.enums import BESSStage, SITE_STAGES, STAGE_TRANSITIONS
from app.shared.exceptions import (
    APINotFoundException,
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


def _mask_phone(phone: str | None) -> str | None:
    if phone is None or len(phone) < 4:
        return phone
    return f"{'*' * max(0, len(phone) - 4)}{phone[-4:]}"


def _ensure_qr_file(serial_number: str) -> tuple[str, Path]:
    media_root = Path(settings.media_root)
    qr_dir = media_root / "qr"
    qr_dir.mkdir(parents=True, exist_ok=True)

    file_name = f"{serial_number}.png"
    file_path = qr_dir / file_name
    public_url = f"/media/qr/{file_name}"

    if settings.qr_code_base_url.rstrip("/").endswith("/api/v1/bess/scan"):
        encoded_url = f"{settings.qr_code_base_url.rstrip('/')}/{serial_number}"
    else:
        encoded_url = f"{settings.qr_code_base_url.rstrip('/')}/api/v1/bess/scan/{serial_number}"

    img = qrcode.make(encoded_url)
    img.save(file_path)
    return public_url, file_path


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

    serial_number = f"BESS-{uuid.uuid4().hex[:12].upper()}"
    qr_code_url, _ = _ensure_qr_file(serial_number)

    async with atomic(db) as session:
        unit = BESSUnit(
            serial_number=serial_number,
            qr_code_url=qr_code_url,
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

    pending = await checklist_repository.get_incomplete_mandatory(db, bess_unit_id, unit.current_stage)
    if pending:
        raise ChecklistIncompleteException(pending)

    async with atomic(db, serializable=True) as session:
        unit.current_stage = to_stage
        if to_stage == BESSStage.ACTIVE:
            unit.is_active = True
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

    if to_stage in SITE_STAGES:
        auto_assign_engineer_task.delay(bess_unit_id, to_stage.value)

    return unit


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
