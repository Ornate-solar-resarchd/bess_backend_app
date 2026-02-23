from __future__ import annotations

from sqlalchemy import Select, func, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.shipment.models import Shipment, ShipmentDocument, ShipmentItem


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

    async def item_exists(self, db: AsyncSession, shipment_id: int, bess_unit_id: int) -> bool:
        stmt = select(ShipmentItem.id).where(
            ShipmentItem.shipment_id == shipment_id,
            ShipmentItem.bess_unit_id == bess_unit_id,
        )
        return (await db.scalar(stmt)) is not None

    async def find_shipment_for_bess(self, db: AsyncSession, bess_unit_id: int) -> int | None:
        stmt = select(ShipmentItem.shipment_id).where(ShipmentItem.bess_unit_id == bess_unit_id).limit(1)
        result = await db.scalar(stmt)
        return int(result) if result is not None else None

    async def count_shipment_items(self, db: AsyncSession, shipment_id: int) -> int:
        total = await db.scalar(select(func.count(ShipmentItem.id)).where(ShipmentItem.shipment_id == shipment_id))
        return int(total or 0)

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

    async def list_all_shipment_items(
        self,
        db: AsyncSession,
        shipment_id: int,
    ) -> list[ShipmentItem]:
        stmt: Select[tuple[ShipmentItem]] = (
            select(ShipmentItem).where(ShipmentItem.shipment_id == shipment_id).order_by(ShipmentItem.id.desc())
        )
        items = (await db.scalars(stmt)).all()
        return list(items)

    async def create_document(self, db: AsyncSession, document: ShipmentDocument) -> ShipmentDocument:
        db.add(document)
        await db.flush()
        return document

    async def count_documents(self, db: AsyncSession, shipment_id: int) -> int:
        total = await db.scalar(select(func.count(ShipmentDocument.id)).where(ShipmentDocument.shipment_id == shipment_id))
        return int(total or 0)

    async def list_documents(
        self,
        db: AsyncSession,
        shipment_id: int,
        page: int,
        size: int,
    ) -> tuple[int, list[ShipmentDocument]]:
        total = await db.scalar(select(func.count(ShipmentDocument.id)).where(ShipmentDocument.shipment_id == shipment_id))
        stmt: Select[tuple[ShipmentDocument]] = (
            select(ShipmentDocument)
            .where(ShipmentDocument.shipment_id == shipment_id)
            .order_by(ShipmentDocument.uploaded_at.desc(), ShipmentDocument.id.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        items = (await db.scalars(stmt)).all()
        return int(total or 0), list(items)

    async def list_all_documents(
        self,
        db: AsyncSession,
        shipment_id: int,
    ) -> list[ShipmentDocument]:
        stmt: Select[tuple[ShipmentDocument]] = (
            select(ShipmentDocument)
            .where(ShipmentDocument.shipment_id == shipment_id)
            .order_by(ShipmentDocument.uploaded_at.desc(), ShipmentDocument.id.desc())
        )
        items = (await db.scalars(stmt)).all()
        return list(items)

    async def list_shipments_for_bess(
        self,
        db: AsyncSession,
        bess_unit_id: int,
        page: int,
        size: int,
    ) -> tuple[int, list[ShipmentItem]]:
        total = await db.scalar(select(func.count(ShipmentItem.id)).where(ShipmentItem.bess_unit_id == bess_unit_id))
        stmt: Select[tuple[ShipmentItem]] = (
            select(ShipmentItem)
            .where(ShipmentItem.bess_unit_id == bess_unit_id)
            .options(selectinload(ShipmentItem.shipment))
            .order_by(ShipmentItem.id.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        items = (await db.scalars(stmt)).all()
        return int(total or 0), list(items)


shipment_repository = ShipmentRepository()
