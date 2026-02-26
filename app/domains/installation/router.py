from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import require_permission
from app.domains.auth.models import User
from app.domains.installation.schemas import (
    ChecklistItemRead,
    ChecklistUpdateRequest,
    ChecklistValidationResponse,
    HandoverDocumentDataRead,
)
from app.domains.installation.service import (
    export_checklist_pdf,
    export_handover_pdf,
    get_handover_document_data,
    get_stage_checklist,
    update_checklist_item,
    validate_stage_checklist,
)
from app.shared.enums import BESSStage

router = APIRouter(prefix="/bess", tags=["Checklists"])


def _to_checklist_item_read(item: object) -> ChecklistItemRead:
    return ChecklistItemRead(
        checklist_template_id=getattr(item, "checklist_template_id"),
        stage=getattr(item, "stage"),
        item_text=getattr(item, "item_text"),
        description=getattr(item, "description"),
        safety_warning=getattr(item, "safety_warning"),
        is_mandatory=getattr(item, "is_mandatory"),
        requires_photo=getattr(item, "requires_photo"),
        order_index=getattr(item, "order_index"),
        is_checked=getattr(item, "is_checked"),
        checked_by_user_id=getattr(item, "checked_by_user_id"),
        checked_at=getattr(item, "checked_at"),
        notes=getattr(item, "notes"),
        photo_url=getattr(item, "photo_url"),
    )


@router.get("/{bess_unit_id}/checklist/{stage}", response_model=list[ChecklistItemRead])
async def get_checklist(
    bess_unit_id: int,
    stage: BESSStage,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("checklist:read")),
) -> list[ChecklistItemRead]:
    items = await get_stage_checklist(db, bess_unit_id, stage)
    return [_to_checklist_item_read(item) for item in items]


@router.patch("/{bess_unit_id}/checklist/{item_id}", response_model=ChecklistItemRead)
async def patch_checklist(
    bess_unit_id: int,
    item_id: int,
    payload: ChecklistUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("checklist:write")),
) -> ChecklistItemRead:
    response = await update_checklist_item(
        db,
        bess_unit_id,
        item_id,
        payload.is_checked,
        payload.notes,
        payload.photo_url,
        current_user,
    )
    items = await get_stage_checklist(db, bess_unit_id, response.stage)
    updated = next((item for item in items if item.checklist_template_id == item_id), None)
    if updated is None:
        return ChecklistItemRead(
            checklist_template_id=item_id,
            stage=response.stage,
            item_text="",
            description=None,
            safety_warning=None,
            is_mandatory=True,
            requires_photo=False,
            order_index=0,
            is_checked=response.is_checked,
            checked_by_user_id=response.checked_by_user_id,
            checked_at=response.checked_at,
            notes=response.notes,
            photo_url=response.photo_url,
        )
    return _to_checklist_item_read(updated)


@router.post("/{bess_unit_id}/checklist/{stage}/validate", response_model=ChecklistValidationResponse)
async def validate_checklist(
    bess_unit_id: int,
    stage: BESSStage,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("checklist:read")),
) -> ChecklistValidationResponse:
    return await validate_stage_checklist(db, bess_unit_id, stage)


@router.get("/{bess_unit_id}/checklist-report/pdf", response_class=FileResponse)
async def download_checklist_pdf(
    bess_unit_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("checklist:read")),
) -> FileResponse:
    report = await export_checklist_pdf(db, bess_unit_id)
    return FileResponse(path=report, media_type="application/pdf", filename=report.name)


@router.get("/{bess_unit_id}/handover-document/pdf", response_class=FileResponse)
async def download_handover_pdf(
    bess_unit_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("checklist:read")),
) -> FileResponse:
    report = await export_handover_pdf(db, bess_unit_id)
    return FileResponse(path=report, media_type="application/pdf", filename=report.name)


@router.get("/{bess_unit_id}/handover-document/data", response_model=HandoverDocumentDataRead)
async def handover_document_data(
    bess_unit_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("checklist:read")),
) -> HandoverDocumentDataRead:
    return await get_handover_document_data(db, bess_unit_id)
