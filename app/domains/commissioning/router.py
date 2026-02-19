from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import require_permission
from app.domains.auth.models import User
from app.domains.commissioning.schemas import (
    CommissioningRecordCreate,
    CommissioningRecordRead,
    PaginatedCommissioningRecords,
)
from app.domains.commissioning.service import create_record, list_records

router = APIRouter(prefix="/commissioning", tags=["Commissioning"])


@router.post("/{bess_unit_id}/records", response_model=CommissioningRecordRead, status_code=status.HTTP_201_CREATED)
async def create_record_endpoint(
    bess_unit_id: int,
    payload: CommissioningRecordCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("bess:transition")),
) -> CommissioningRecordRead:
    record = await create_record(db, bess_unit_id, payload, current_user)
    return CommissioningRecordRead.model_validate(record)


@router.get("/{bess_unit_id}/records", response_model=PaginatedCommissioningRecords)
async def list_records_endpoint(
    bess_unit_id: int,
    page: int = 1,
    size: int = 20,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("bess:read")),
) -> PaginatedCommissioningRecords:
    total, items = await list_records(db, bess_unit_id, page, size)
    return PaginatedCommissioningRecords(
        total=total,
        items=[CommissioningRecordRead.model_validate(i) for i in items],
        page=page,
        size=size,
    )
