from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.auth.models import User
from app.domains.bess_unit.models import AuditLog
from app.domains.bess_unit.repository import bess_repository
from app.domains.master.models import Country
from app.domains.shipment.models import Shipment, ShipmentItem
from app.domains.shipment.repository import shipment_repository
from app.domains.shipment.schemas import ShipmentCreate
from app.shared.acid import atomic
from app.shared.enums import BESSStage, ShipmentStatus
from app.shared.exceptions import APIConflictException, APINotFoundException


STATUS_TO_BESS_STAGE: dict[ShipmentStatus, BESSStage] = {
    ShipmentStatus.PACKED: BESSStage.PACKED,
    ShipmentStatus.IN_TRANSIT: BESSStage.IN_TRANSIT,
    ShipmentStatus.ARRIVED: BESSStage.PORT_ARRIVED,
}


async def create_shipment(db: AsyncSession, payload: ShipmentCreate, current_user: User):
    duplicate = await db.scalar(select(Shipment).where(Shipment.shipment_code == payload.shipment_code))
    if duplicate:
        raise APIConflictException("Shipment code already exists")
    if not await db.get(Country, payload.origin_country_id):
        raise APINotFoundException("Origin country not found")
    if not await db.get(Country, payload.destination_country_id):
        raise APINotFoundException("Destination country not found")

    async with atomic(db) as session:
        shipment = await shipment_repository.create_shipment(
            session,
            Shipment(
                shipment_code=payload.shipment_code,
                origin_country_id=payload.origin_country_id,
                destination_country_id=payload.destination_country_id,
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


async def assign_unit_to_shipment(
    db: AsyncSession,
    shipment_id: int,
    bess_unit_id: int,
    current_user: User,
):
    shipment = await shipment_repository.get_shipment(db, shipment_id)
    if shipment is None:
        raise APINotFoundException("Shipment not found")

    unit = await bess_repository.get_by_id(db, bess_unit_id)
    if unit is None or unit.is_deleted:
        raise APINotFoundException("BESS unit not found")

    async with atomic(db) as session:
        item = await shipment_repository.add_unit_to_shipment(session, shipment_id, bess_unit_id)
        unit.current_stage = BESSStage.SHIPMENT_ASSIGNED
        await session.flush()
        await bess_repository.create_audit_log(
            session,
            AuditLog(
                user_id=current_user.id,
                action="SHIPMENT_ADD_UNIT",
                entity_type="ShipmentItem",
                entity_id=item.id,
                payload_json={"shipment_id": shipment_id, "bess_unit_id": bess_unit_id},
            ),
        )
    return item


async def update_shipment_status(
    db: AsyncSession,
    shipment_id: int,
    status: ShipmentStatus,
    current_user: User,
):
    shipment = await shipment_repository.get_shipment(db, shipment_id)
    if shipment is None:
        raise APINotFoundException("Shipment not found")

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
