from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import require_permission
from app.domains.auth.models import User
from app.domains.shipment.schemas import (
    ShipmentDetailRead,
    PaginatedShipmentDocuments,
    PaginatedShipmentItems,
    PaginatedShipments,
    ShipmentBulkItemAssign,
    ShipmentCreate,
    ShipmentDocumentRead,
    ShipmentItemAssign,
    ShipmentSiteAssign,
    ShipmentRead,
    ShipmentStatusUpdate,
    ShipmentWarehouseAssign,
)
from app.domains.shipment.service import (
    assign_unit_to_shipment,
    assign_shipment_site,
    assign_shipment_warehouse,
    assign_units_to_shipment_bulk,
    create_shipment,
    get_shipment_detail,
    list_shipment_documents,
    list_shipment_units,
    list_shipments,
    upload_shipment_document,
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


@router.get("/{shipment_id}", response_model=ShipmentDetailRead)
async def get_shipment_detail_endpoint(
    shipment_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("shipment:read")),
) -> ShipmentDetailRead:
    return await get_shipment_detail(db, shipment_id)


@router.post("/{shipment_id}/units", status_code=status.HTTP_204_NO_CONTENT)
async def assign_unit_endpoint(
    shipment_id: int,
    payload: ShipmentItemAssign,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("shipment:manage")),
) -> Response:
    await assign_unit_to_shipment(db, shipment_id, payload.bess_unit_id, payload.order_id, current_user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{shipment_id}/units/bulk", status_code=status.HTTP_204_NO_CONTENT)
async def bulk_assign_units_endpoint(
    shipment_id: int,
    payload: ShipmentBulkItemAssign,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("shipment:manage")),
) -> Response:
    await assign_units_to_shipment_bulk(db, shipment_id, payload, current_user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{shipment_id}/units", response_model=PaginatedShipmentItems)
async def list_shipment_units_endpoint(
    shipment_id: int,
    page: int = 1,
    size: int = 20,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("shipment:read")),
) -> PaginatedShipmentItems:
    return await list_shipment_units(db, shipment_id, page, size)


@router.patch("/{shipment_id}/warehouse", response_model=ShipmentRead)
async def assign_shipment_warehouse_endpoint(
    shipment_id: int,
    payload: ShipmentWarehouseAssign,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("shipment:manage")),
) -> ShipmentRead:
    shipment = await assign_shipment_warehouse(db, shipment_id, payload, current_user)
    return ShipmentRead.model_validate(shipment)


@router.patch("/{shipment_id}/site", response_model=ShipmentRead)
async def assign_shipment_site_endpoint(
    shipment_id: int,
    payload: ShipmentSiteAssign,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("shipment:manage")),
) -> ShipmentRead:
    shipment = await assign_shipment_site(db, shipment_id, payload, current_user)
    return ShipmentRead.model_validate(shipment)


@router.post("/{shipment_id}/documents/upload", response_model=ShipmentDocumentRead, status_code=status.HTTP_201_CREATED)
async def upload_shipment_document_endpoint(
    shipment_id: int,
    file: UploadFile = File(...),
    document_type: str | None = Form(default=None),
    document_name: str | None = Form(default=None),
    notes: str | None = Form(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("shipment:manage")),
) -> ShipmentDocumentRead:
    document = await upload_shipment_document(
        db,
        shipment_id,
        file,
        document_type,
        notes,
        current_user,
        document_name,
    )
    return ShipmentDocumentRead.model_validate(document)


@router.get("/{shipment_id}/documents", response_model=PaginatedShipmentDocuments)
async def list_shipment_documents_endpoint(
    shipment_id: int,
    page: int = 1,
    size: int = 20,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("shipment:read")),
) -> PaginatedShipmentDocuments:
    return await list_shipment_documents(db, shipment_id, page, size)


@router.patch("/{shipment_id}/status", response_model=ShipmentRead)
async def update_status_endpoint(
    shipment_id: int,
    payload: ShipmentStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("shipment:manage")),
) -> ShipmentRead:
    shipment = await update_shipment_status(db, shipment_id, payload.status, current_user)
    return ShipmentRead.model_validate(shipment)
