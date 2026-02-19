from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import require_permission
from app.domains.auth.models import User
from app.domains.shipment.schemas import (
    PaginatedShipments,
    ShipmentCreate,
    ShipmentItemAssign,
    ShipmentRead,
    ShipmentStatusUpdate,
)
from app.domains.shipment.service import (
    assign_unit_to_shipment,
    create_shipment,
    list_shipments,
    update_shipment_status,
)

router = APIRouter(prefix="/shipments", tags=["Shipments"])


@router.post("/", response_model=ShipmentRead, status_code=status.HTTP_201_CREATED)
async def create_shipment_endpoint(
    payload: ShipmentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("shipment:manage")),
) -> ShipmentRead:
    shipment = await create_shipment(db, payload, current_user)
    return ShipmentRead.model_validate(shipment)


@router.get("/", response_model=PaginatedShipments)
async def list_shipments_endpoint(
    page: int = 1,
    size: int = 20,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("shipment:read")),
) -> PaginatedShipments:
    total, items = await list_shipments(db, page, size)
    return PaginatedShipments(total=total, items=[ShipmentRead.model_validate(i) for i in items], page=page, size=size)


@router.post("/{shipment_id}/units", status_code=status.HTTP_204_NO_CONTENT)
async def assign_unit_endpoint(
    shipment_id: int,
    payload: ShipmentItemAssign,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("shipment:manage")),
) -> Response:
    await assign_unit_to_shipment(db, shipment_id, payload.bess_unit_id, current_user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/{shipment_id}/status", response_model=ShipmentRead)
async def update_status_endpoint(
    shipment_id: int,
    payload: ShipmentStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("shipment:manage")),
) -> ShipmentRead:
    shipment = await update_shipment_status(db, shipment_id, payload.status, current_user)
    return ShipmentRead.model_validate(shipment)
