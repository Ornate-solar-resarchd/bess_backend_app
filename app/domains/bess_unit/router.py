from __future__ import annotations

from fastapi import APIRouter, Depends, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import AuthContext, get_auth_context, get_current_user, require_permission
from app.domains.auth.models import User
from app.domains.bess_unit import service
from app.domains.bess_unit.schemas import (
    BESSUnitCreate,
    BESSUnitRead,
    BESSUnitUpdate,
    PaginatedBESSUnits,
    ScanResponse,
    StageHistoryRead,
    StageTransitionRequest,
)
from app.shared.enums import BESSStage

router = APIRouter(prefix="/bess", tags=["BESS Unit"])


@router.post("/", response_model=BESSUnitRead, status_code=status.HTTP_201_CREATED)
async def create_unit(
    payload: BESSUnitCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("bess:create")),
) -> BESSUnitRead:
    obj = await service.create_bess_unit(db, payload, current_user)
    return BESSUnitRead.model_validate(obj)


@router.get("/", response_model=PaginatedBESSUnits)
async def list_units(
    city_id: int | None = None,
    country_id: int | None = None,
    stage: BESSStage | None = None,
    serial: str | None = None,
    page: int = 1,
    size: int = 20,
    db: AsyncSession = Depends(get_db),
    context: AuthContext = Depends(get_auth_context),
    _: User = Depends(require_permission("bess:read")),
) -> PaginatedBESSUnits:
    customer_filter = context.user.id if "CUSTOMER" in context.roles else None
    total, items = await service.list_bess_units(
        db,
        page,
        size,
        city_id,
        country_id,
        stage,
        serial,
        customer_filter,
    )
    return PaginatedBESSUnits(
        total=total,
        items=[BESSUnitRead.model_validate(item) for item in items],
        page=page,
        size=size,
    )


@router.get("/{bess_unit_id}", response_model=BESSUnitRead)
async def get_unit(
    bess_unit_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("bess:read")),
) -> BESSUnitRead:
    obj = await service.get_bess_unit(db, bess_unit_id)
    return BESSUnitRead.model_validate(obj)


@router.get("/scan/{serial_number}", response_model=ScanResponse)
async def scan(serial_number: str, db: AsyncSession = Depends(get_db)) -> ScanResponse:
    return await service.scan_by_serial(db, serial_number)


@router.get("/{bess_unit_id}/qrcode", response_class=FileResponse)
async def get_qrcode(
    bess_unit_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("bess:read")),
) -> FileResponse:
    return await service.get_qr_code_file(db, bess_unit_id)


@router.patch("/{bess_unit_id}", response_model=BESSUnitRead)
async def update_unit(
    bess_unit_id: int,
    payload: BESSUnitUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("bess:create")),
) -> BESSUnitRead:
    obj = await service.update_bess_unit(db, bess_unit_id, payload, current_user)
    return BESSUnitRead.model_validate(obj)


@router.patch("/{bess_unit_id}/transition", response_model=BESSUnitRead)
async def transition_unit(
    bess_unit_id: int,
    payload: StageTransitionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("bess:transition")),
) -> BESSUnitRead:
    obj = await service.transition_stage(
        bess_unit_id=bess_unit_id,
        to_stage=payload.to_stage,
        notes=payload.notes,
        current_user=current_user,
        db=db,
    )
    return BESSUnitRead.model_validate(obj)


@router.get("/{bess_unit_id}/history", response_model=list[StageHistoryRead])
async def history(
    bess_unit_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("bess:read")),
) -> list[StageHistoryRead]:
    records = await service.list_stage_history(db, bess_unit_id)
    return [StageHistoryRead.model_validate(record) for record in records]
