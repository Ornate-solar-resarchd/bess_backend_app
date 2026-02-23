from __future__ import annotations

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.shipment.models import Shipment, ShipmentItem


class ShipmentRepository:
    async def create_shipment(self, db: AsyncSession, shipment: Shipment) -> Shipment:
        db.add(shipment)
        await db.flush()
        return shipment

    async def list_shipments(self, db: AsyncSession, page: int, size: int) -> tuple[int, list[Shipment]]:
        total = await db.scalar(select(func.count(Shipment.id)))
        stmt: Select[tuple[Shipment]] = (
            select(Shipment).order_by(Shipment.id.desc()).offset((page - 1) * size).limit(size)
        )
        items = (await db.scalars(stmt)).all()
        return int(total or 0), list(items)

    async def get_shipment(self, db: AsyncSession, shipment_id: int) -> Shipment | None:
        return await db.get(Shipment, shipment_id)

    async def add_unit_to_shipment(
        self,
        db: AsyncSession,
        shipment_id: int,
        bess_unit_id: int,
        order_id: str,
    ) -> ShipmentItem:
        entity = ShipmentItem(shipment_id=shipment_id, bess_unit_id=bess_unit_id, order_id=order_id)
        db.add(entity)
        await db.flush()
        return entity

    async def list_shipment_items(
        self,
        db: AsyncSession,
        shipment_id: int,
        page: int,
        size: int,
    ) -> tuple[int, list[ShipmentItem]]:
        total = await db.scalar(select(func.count(ShipmentItem.id)).where(ShipmentItem.shipment_id == shipment_id))
        stmt: Select[tuple[ShipmentItem]] = (
            select(ShipmentItem)
            .where(ShipmentItem.shipment_id == shipment_id)
            .order_by(ShipmentItem.id.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        items = (await db.scalars(stmt)).all()
        return int(total or 0), list(items)


shipment_repository = ShipmentRepository()
