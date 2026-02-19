from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.auth.models import User
from app.domains.bess_unit.models import AuditLog
from app.domains.bess_unit.repository import bess_repository
from app.domains.commissioning.models import CommissioningRecord
from app.domains.commissioning.repository import commissioning_repository
from app.domains.commissioning.schemas import CommissioningRecordCreate
from app.shared.acid import atomic
from app.shared.enums import BESSStage
from app.shared.exceptions import BESSNotFoundException


COMMISSIONING_STAGES = {
    BESSStage.PRE_COMMISSION,
    BESSStage.COLD_COMMISSION,
    BESSStage.HOT_COMMISSION,
    BESSStage.FINAL_ACCEPTANCE,
}


async def create_record(
    db: AsyncSession,
    bess_unit_id: int,
    payload: CommissioningRecordCreate,
    current_user: User,
):
    unit = await bess_repository.get_by_id(db, bess_unit_id)
    if unit is None or unit.is_deleted:
        raise BESSNotFoundException(bess_unit_id)
    if payload.stage not in COMMISSIONING_STAGES:
        raise ValueError("Invalid commissioning stage")

    async with atomic(db) as session:
        record = await commissioning_repository.create(
            session,
            CommissioningRecord(
                bess_unit_id=bess_unit_id,
                stage=payload.stage,
                status=payload.status,
                notes=payload.notes,
                recorded_by_user_id=current_user.id,
            ),
        )
        await bess_repository.create_audit_log(
            session,
            AuditLog(
                user_id=current_user.id,
                action="COMMISSIONING_RECORD_CREATE",
                entity_type="CommissioningRecord",
                entity_id=record.id,
                payload_json={"stage": payload.stage.value, "status": payload.status},
            ),
        )
    return record


async def list_records(db: AsyncSession, bess_unit_id: int, page: int, size: int):
    unit = await bess_repository.get_by_id(db, bess_unit_id)
    if unit is None or unit.is_deleted:
        raise BESSNotFoundException(bess_unit_id)
    return await commissioning_repository.list_by_bess(db, bess_unit_id, page, size)
