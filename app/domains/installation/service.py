from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.auth.models import User
from app.domains.bess_unit.models import AuditLog
from app.domains.bess_unit.repository import bess_repository
from app.domains.installation.models import ChecklistResponse, ChecklistTemplate
from app.domains.installation.repository import checklist_repository
from app.domains.installation.schemas import ChecklistValidationResponse
from app.shared.acid import atomic
from app.shared.enums import BESSStage
from app.shared.exceptions import APINotFoundException, BESSNotFoundException


async def get_stage_checklist(db: AsyncSession, bess_unit_id: int, stage: BESSStage):
    unit = await bess_repository.get_by_id(db, bess_unit_id)
    if unit is None or unit.is_deleted:
        raise BESSNotFoundException(bess_unit_id)
    return await checklist_repository.get_stage_items(db, bess_unit_id, stage)


async def update_checklist_item(
    db: AsyncSession,
    bess_unit_id: int,
    checklist_template_id: int,
    is_checked: bool,
    notes: str | None,
    photo_url: str | None,
    current_user: User,
) -> ChecklistResponse:
    unit = await bess_repository.get_by_id(db, bess_unit_id)
    if unit is None or unit.is_deleted:
        raise BESSNotFoundException(bess_unit_id)

    template = await db.get(ChecklistTemplate, checklist_template_id)
    if template is None:
        raise APINotFoundException("Checklist template item not found")

    async with atomic(db) as session:
        response = await checklist_repository.get_response(session, bess_unit_id, checklist_template_id)
        if response is None:
            response = await checklist_repository.create_response(session, bess_unit_id, template)

        response.is_checked = is_checked
        response.notes = notes
        response.photo_url = photo_url
        response.checked_by_user_id = current_user.id if is_checked else None
        response.checked_at = datetime.now(UTC) if is_checked else None
        await session.flush()

        await bess_repository.create_audit_log(
            session,
            AuditLog(
                user_id=current_user.id,
                action="CHECKLIST_UPDATE",
                entity_type="ChecklistResponse",
                entity_id=response.id,
                payload_json={
                    "bess_unit_id": bess_unit_id,
                    "checklist_template_id": checklist_template_id,
                    "is_checked": is_checked,
                },
            ),
        )

    return response


async def validate_stage_checklist(
    db: AsyncSession,
    bess_unit_id: int,
    stage: BESSStage,
) -> ChecklistValidationResponse:
    unit = await bess_repository.get_by_id(db, bess_unit_id)
    if unit is None or unit.is_deleted:
        raise BESSNotFoundException(bess_unit_id)

    pending = await checklist_repository.get_incomplete_mandatory(db, bess_unit_id, stage)
    return ChecklistValidationResponse(all_complete=not pending, pending_items=pending)
