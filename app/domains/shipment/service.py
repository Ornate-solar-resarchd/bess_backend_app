from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.domains.auth.models import User
from app.domains.bess_unit.models import AuditLog
from app.domains.bess_unit.repository import bess_repository
from app.domains.master.models import Country, Site, Warehouse
from app.domains.shipment.models import Shipment, ShipmentDocument, ShipmentItem
from app.domains.shipment.repository import shipment_repository
from app.domains.shipment.schemas import (
    PaginatedShipmentDocuments,
    PaginatedShipmentItems,
    ShipmentBulkItemAssign,
    ShipmentCreate,
    ShipmentDetailRead,
    ShipmentDocumentRead,
    ShipmentItemRead,
    ShipmentRead,
    ShipmentSiteAssign,
    ShipmentWarehouseAssign,
)
from app.services.s3 import is_s3_media_enabled, upload_bytes_to_s3
from app.shared.acid import atomic
from app.shared.enums import BESSStage, ShipmentStatus
from app.shared.exceptions import APIConflictException, APINotFoundException, APIValidationException


STATUS_TO_BESS_STAGE: dict[ShipmentStatus, BESSStage] = {
    ShipmentStatus.PACKED: BESSStage.PACKED,
    ShipmentStatus.IN_TRANSIT: BESSStage.IN_TRANSIT,
    ShipmentStatus.ARRIVED: BESSStage.PORT_ARRIVED,
    ShipmentStatus.PORT_CLEARED: BESSStage.PORT_CLEARED,
    ShipmentStatus.WAREHOUSE_STORED: BESSStage.WAREHOUSE_STORED,
    ShipmentStatus.DISPATCHED_TO_SITE: BESSStage.DISPATCHED_TO_SITE,
    ShipmentStatus.SITE_ARRIVED: BESSStage.SITE_ARRIVED,
}

ALLOWED_SHIPMENT_TRANSITIONS: dict[ShipmentStatus, ShipmentStatus] = {
    ShipmentStatus.CREATED: ShipmentStatus.PACKED,
    ShipmentStatus.PACKED: ShipmentStatus.IN_TRANSIT,
    ShipmentStatus.IN_TRANSIT: ShipmentStatus.ARRIVED,
    ShipmentStatus.ARRIVED: ShipmentStatus.PORT_CLEARED,
    ShipmentStatus.PORT_CLEARED: ShipmentStatus.WAREHOUSE_STORED,
    ShipmentStatus.WAREHOUSE_STORED: ShipmentStatus.DISPATCHED_TO_SITE,
    ShipmentStatus.DISPATCHED_TO_SITE: ShipmentStatus.SITE_ARRIVED,
}

PORT_CLEARED_DOCUMENT_TYPE = "PORT_CLEARED"


def _sanitize_filename(raw_name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", raw_name).strip("._")
    return cleaned or "document"


async def create_shipment(db: AsyncSession, payload: ShipmentCreate, current_user: User):
    warehouse_id = getattr(payload, "warehouse_id", None)
    site_id = getattr(payload, "site_id", None)
    duplicate = await db.scalar(select(Shipment).where(Shipment.shipment_code == payload.shipment_code))
    if duplicate:
        raise APIConflictException("Shipment code already exists")
    if not await db.get(Country, payload.origin_country_id):
        raise APINotFoundException("Origin country not found")
    if not await db.get(Country, payload.destination_country_id):
        raise APINotFoundException("Destination country not found")
    if warehouse_id is not None and not await db.get(Warehouse, warehouse_id):
        raise APINotFoundException("Warehouse not found")
    if site_id is not None and not await db.get(Site, site_id):
        raise APINotFoundException("Site not found")

    async with atomic(db) as session:
        shipment = await shipment_repository.create_shipment(
            session,
            Shipment(
                shipment_code=payload.shipment_code,
                origin_country_id=payload.origin_country_id,
                destination_country_id=payload.destination_country_id,
                warehouse_id=warehouse_id,
                site_id=site_id,
                created_date=payload.created_date or datetime.now(UTC).date(),
                expected_arrival_date=payload.expected_arrival_date,
                expected_quantity=payload.expected_quantity,
                status=ShipmentStatus.CREATED,
            ),
        )
        await bess_repository.create_audit_log(
            session,
            AuditLog(
                user_id=current_user.id,
                action="SHIPMENT_CREATE",
                entity_type="Shipment",
                entity_id=shipment.id,
                payload_json={"shipment_code": shipment.shipment_code},
            ),
        )
    return shipment


async def list_shipments(db: AsyncSession, page: int, size: int):
    return await shipment_repository.list_shipments(db, page, size)


async def get_shipment_detail(db: AsyncSession, shipment_id: int) -> ShipmentDetailRead:
    shipment = await shipment_repository.get_shipment(db, shipment_id)
    if shipment is None:
        raise APINotFoundException("Shipment not found")
    units = await shipment_repository.list_all_shipment_items(db, shipment_id)
    documents = await shipment_repository.list_all_documents(db, shipment_id)
    return ShipmentDetailRead(
        shipment=ShipmentRead.model_validate(shipment),
        units_total=len(units),
        units=[ShipmentItemRead.model_validate(item) for item in units],
        documents_total=len(documents),
        documents=[ShipmentDocumentRead.model_validate(item) for item in documents],
    )


async def assign_unit_to_shipment(
    db: AsyncSession,
    shipment_id: int,
    bess_unit_id: int,
    order_id: str,
    current_user: User,
):
    shipment = await shipment_repository.get_shipment(db, shipment_id)
    if shipment is None:
        raise APINotFoundException("Shipment not found")

    unit = await bess_repository.get_by_id(db, bess_unit_id)
    if unit is None or unit.is_deleted:
        raise APINotFoundException("BESS unit not found")
    if await shipment_repository.item_exists(db, shipment_id, bess_unit_id):
        raise APIConflictException("This BESS unit is already linked to this shipment")
    existing_shipment_id = await shipment_repository.find_shipment_for_bess(db, bess_unit_id)
    if existing_shipment_id is not None and existing_shipment_id != shipment_id:
        raise APIConflictException(
            f"BESS unit {bess_unit_id} is already linked to shipment {existing_shipment_id}"
        )
    normalized_order_id = order_id.strip()
    if not normalized_order_id:
        raise APIValidationException("order_id is required")

    async with atomic(db) as session:
        item = await shipment_repository.add_unit_to_shipment(
            session,
            shipment_id,
            bess_unit_id,
            normalized_order_id,
        )
        unit.current_stage = BESSStage.SHIPMENT_ASSIGNED
        await session.flush()
        await bess_repository.create_audit_log(
            session,
            AuditLog(
                user_id=current_user.id,
                action="SHIPMENT_ADD_UNIT",
                entity_type="ShipmentItem",
                entity_id=item.id,
                payload_json={
                    "shipment_id": shipment_id,
                    "bess_unit_id": bess_unit_id,
                    "order_id": normalized_order_id,
                },
            ),
        )
    return item


async def assign_units_to_shipment_bulk(
    db: AsyncSession,
    shipment_id: int,
    payload: ShipmentBulkItemAssign,
    current_user: User,
) -> int:
    shipment = await shipment_repository.get_shipment(db, shipment_id)
    if shipment is None:
        raise APINotFoundException("Shipment not found")
    if not payload.items:
        raise APIValidationException("items cannot be empty")

    seen_bess_ids: set[int] = set()
    for item in payload.items:
        normalized_order_id = item.order_id.strip()
        if not normalized_order_id:
            raise APIValidationException("order_id is required for every item")
        if item.bess_unit_id in seen_bess_ids:
            raise APIValidationException(f"Duplicate bess_unit_id in request: {item.bess_unit_id}")
        seen_bess_ids.add(item.bess_unit_id)
        unit = await bess_repository.get_by_id(db, item.bess_unit_id)
        if unit is None or unit.is_deleted:
            raise APINotFoundException(f"BESS unit not found: {item.bess_unit_id}")
        if await shipment_repository.item_exists(db, shipment_id, item.bess_unit_id):
            raise APIConflictException(f"BESS unit already linked to shipment: {item.bess_unit_id}")
        existing_shipment_id = await shipment_repository.find_shipment_for_bess(db, item.bess_unit_id)
        if existing_shipment_id is not None and existing_shipment_id != shipment_id:
            raise APIConflictException(
                f"BESS unit {item.bess_unit_id} is already linked to shipment {existing_shipment_id}"
            )

    created_items = 0
    async with atomic(db) as session:
        for item in payload.items:
            normalized_order_id = item.order_id.strip()
            created = await shipment_repository.add_unit_to_shipment(
                session,
                shipment_id,
                item.bess_unit_id,
                normalized_order_id,
            )
            unit = await bess_repository.get_by_id(session, item.bess_unit_id)
            if unit is not None and not unit.is_deleted:
                unit.current_stage = BESSStage.SHIPMENT_ASSIGNED
            created_items += 1
            await bess_repository.create_audit_log(
                session,
                AuditLog(
                    user_id=current_user.id,
                    action="SHIPMENT_ADD_UNIT",
                    entity_type="ShipmentItem",
                    entity_id=created.id,
                    payload_json={
                        "shipment_id": shipment_id,
                        "bess_unit_id": item.bess_unit_id,
                        "order_id": normalized_order_id,
                    },
                ),
            )
        await session.flush()
        await bess_repository.create_audit_log(
            session,
            AuditLog(
                user_id=current_user.id,
                action="SHIPMENT_BULK_ADD_UNITS",
                entity_type="Shipment",
                entity_id=shipment_id,
                payload_json={"count": created_items},
            ),
        )
    return created_items


async def list_shipment_units(
    db: AsyncSession,
    shipment_id: int,
    page: int,
    size: int,
) -> PaginatedShipmentItems:
    shipment = await shipment_repository.get_shipment(db, shipment_id)
    if shipment is None:
        raise APINotFoundException("Shipment not found")
    total, items = await shipment_repository.list_shipment_items(db, shipment_id, page, size)
    return PaginatedShipmentItems(
        total=total,
        items=[ShipmentItemRead.model_validate(item) for item in items],
        page=page,
        size=size,
    )


async def assign_shipment_warehouse(
    db: AsyncSession,
    shipment_id: int,
    payload: ShipmentWarehouseAssign,
    current_user: User,
) -> Shipment:
    shipment = await shipment_repository.get_shipment(db, shipment_id)
    if shipment is None:
        raise APINotFoundException("Shipment not found")
    warehouse = await db.get(Warehouse, payload.warehouse_id)
    if warehouse is None:
        raise APINotFoundException("Warehouse not found")

    linked_items = await shipment_repository.list_all_shipment_items(db, shipment_id)
    async with atomic(db) as session:
        shipment.warehouse_id = warehouse.id
        for item in linked_items:
            unit = await bess_repository.get_by_id(session, item.bess_unit_id)
            if unit is not None and not unit.is_deleted:
                unit.warehouse_id = warehouse.id
        await session.flush()
        await bess_repository.create_audit_log(
            session,
            AuditLog(
                user_id=current_user.id,
                action="SHIPMENT_WAREHOUSE_ASSIGN",
                entity_type="Shipment",
                entity_id=shipment.id,
                payload_json={"warehouse_id": warehouse.id},
            ),
        )
    return shipment


async def assign_shipment_site(
    db: AsyncSession,
    shipment_id: int,
    payload: ShipmentSiteAssign,
    current_user: User,
) -> Shipment:
    shipment = await shipment_repository.get_shipment(db, shipment_id)
    if shipment is None:
        raise APINotFoundException("Shipment not found")
    site = await db.get(Site, payload.site_id)
    if site is None:
        raise APINotFoundException("Site not found")

    linked_items = await shipment_repository.list_all_shipment_items(db, shipment_id)
    async with atomic(db) as session:
        shipment.site_id = site.id
        shipment.destination_country_id = site.country_id
        for item in linked_items:
            unit = await bess_repository.get_by_id(session, item.bess_unit_id)
            if unit is not None and not unit.is_deleted:
                unit.country_id = site.country_id
                unit.city_id = site.city_id
                unit.site_address = site.address
                unit.site_latitude = site.latitude
                unit.site_longitude = site.longitude
        await session.flush()
        await bess_repository.create_audit_log(
            session,
            AuditLog(
                user_id=current_user.id,
                action="SHIPMENT_SITE_ASSIGN",
                entity_type="Shipment",
                entity_id=shipment.id,
                payload_json={"site_id": site.id},
            ),
        )
    return shipment


async def update_shipment_status(
    db: AsyncSession,
    shipment_id: int,
    status: ShipmentStatus,
    current_user: User,
):
    shipment = await shipment_repository.get_shipment(db, shipment_id)
    if shipment is None:
        raise APINotFoundException("Shipment not found")

    if shipment.status != status:
        next_status = ALLOWED_SHIPMENT_TRANSITIONS.get(shipment.status)
        if next_status != status:
            raise APIValidationException(
                f"Invalid shipment status transition from {shipment.status.value} to {status.value}"
            )

    if status == ShipmentStatus.PACKED:
        item_count = await shipment_repository.count_shipment_items(db, shipment_id)
        if item_count < shipment.expected_quantity:
            raise APIConflictException(
                f"Cannot mark PACKED. expected_quantity={shipment.expected_quantity}, assigned_units={item_count}"
            )
        doc_count = await shipment_repository.count_documents(db, shipment_id)
        if doc_count < 1:
            raise APIConflictException("Cannot mark PACKED. Upload shipment documents first.")
    if status == ShipmentStatus.PORT_CLEARED:
        cleared_doc_count = await shipment_repository.count_documents_by_type(
            db,
            shipment_id,
            PORT_CLEARED_DOCUMENT_TYPE,
        )
        if cleared_doc_count < 1:
            raise APIConflictException(
                "Cannot mark PORT_CLEARED. Upload at least one PORT_CLEARED document first."
            )
    if status == ShipmentStatus.WAREHOUSE_STORED and shipment.warehouse_id is None:
        raise APIConflictException("Cannot mark WAREHOUSE_STORED. Assign warehouse to shipment first.")
    if status == ShipmentStatus.DISPATCHED_TO_SITE and shipment.site_id is None:
        raise APIConflictException("Cannot mark DISPATCHED_TO_SITE. Assign site to shipment first.")

    async with atomic(db) as session:
        shipment.status = status
        await session.flush()

        if status in STATUS_TO_BESS_STAGE:
            stage = STATUS_TO_BESS_STAGE[status]
            rows = (await session.execute(select(ShipmentItem).where(ShipmentItem.shipment_id == shipment.id))).scalars().all()
            for item in rows:
                unit = await bess_repository.get_by_id(session, item.bess_unit_id)
                if unit is not None and not unit.is_deleted:
                    unit.current_stage = stage
            await session.flush()

        await bess_repository.create_audit_log(
            session,
            AuditLog(
                user_id=current_user.id,
                action="SHIPMENT_STATUS_UPDATE",
                entity_type="Shipment",
                entity_id=shipment.id,
                payload_json={"status": status.value},
            ),
        )

    return shipment


async def upload_shipment_document(
    db: AsyncSession,
    shipment_id: int,
    file: UploadFile,
    document_type: str | None,
    notes: str | None,
    current_user: User,
    document_name: str | None = None,
) -> ShipmentDocument:
    shipment = await shipment_repository.get_shipment(db, shipment_id)
    if shipment is None:
        raise APINotFoundException("Shipment not found")
    if not file.filename:
        raise APIValidationException("file is required")

    content = await file.read()
    if not content:
        raise APIValidationException("Uploaded file is empty")

    if is_s3_media_enabled():
        public_url = upload_bytes_to_s3(
            content=content,
            original_filename=file.filename,
            folder=f"shipment_documents/{shipment_id}",
            content_type=file.content_type,
        )
    else:
        ext = Path(file.filename).suffix
        saved_name = f"{uuid4().hex}{ext.lower()}"
        base_dir = Path(settings.media_root) / "shipment_documents" / str(shipment_id)
        base_dir.mkdir(parents=True, exist_ok=True)
        file_path = base_dir / saved_name
        file_path.write_bytes(content)
        public_url = f"/media/shipment_documents/{shipment_id}/{saved_name}"

    raw_name = (document_name or file.filename).strip()
    normalized_name = _sanitize_filename(raw_name)
    normalized_doc_type = document_type.strip() if document_type else None
    normalized_notes = notes.strip() if notes else None

    async with atomic(db) as session:
        document = await shipment_repository.create_document(
            session,
            ShipmentDocument(
                shipment_id=shipment_id,
                document_name=normalized_name,
                document_type=normalized_doc_type,
                document_url=public_url,
                notes=normalized_notes,
                uploaded_by_user_id=current_user.id,
            ),
        )
        await bess_repository.create_audit_log(
            session,
            AuditLog(
                user_id=current_user.id,
                action="SHIPMENT_DOCUMENT_UPLOAD",
                entity_type="ShipmentDocument",
                entity_id=document.id,
                payload_json={
                    "shipment_id": shipment_id,
                    "document_name": normalized_name,
                    "document_type": normalized_doc_type,
                    "document_url": public_url,
                },
            ),
        )
    return document


async def list_shipment_documents(
    db: AsyncSession,
    shipment_id: int,
    page: int,
    size: int,
) -> PaginatedShipmentDocuments:
    shipment = await shipment_repository.get_shipment(db, shipment_id)
    if shipment is None:
        raise APINotFoundException("Shipment not found")
    total, items = await shipment_repository.list_documents(db, shipment_id, page, size)
    return PaginatedShipmentDocuments(
        total=total,
        items=[ShipmentDocumentRead.model_validate(item) for item in items],
        page=page,
        size=size,
    )
