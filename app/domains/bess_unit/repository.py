from __future__ import annotations

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.bess_unit.models import AuditLog, BESSUnit, StageHistory
from app.shared.enums import BESSStage


class BESSRepository:
    async def create(self, db: AsyncSession, unit: BESSUnit) -> BESSUnit:
        db.add(unit)
        await db.flush()
        await db.refresh(unit)
        return unit

    async def get_by_id(self, db: AsyncSession, bess_unit_id: int) -> BESSUnit | None:
        return await db.get(BESSUnit, bess_unit_id)

    async def get_by_serial(self, db: AsyncSession, serial_number: str) -> BESSUnit | None:
        stmt = select(BESSUnit).where(BESSUnit.serial_number == serial_number, BESSUnit.is_deleted.is_(False))
        return await db.scalar(stmt)

    async def list_units(
        self,
        db: AsyncSession,
        page: int,
        size: int,
        city_id: int | None,
        country_id: int | None,
        stage: BESSStage | None,
        serial: str | None,
        customer_user_id: int | None,
    ) -> tuple[int, list[BESSUnit]]:
        count_stmt = select(func.count(BESSUnit.id)).where(BESSUnit.is_deleted.is_(False))
        stmt: Select[tuple[BESSUnit]] = select(BESSUnit).where(BESSUnit.is_deleted.is_(False))

        if city_id is not None:
            count_stmt = count_stmt.where(BESSUnit.city_id == city_id)
            stmt = stmt.where(BESSUnit.city_id == city_id)
        if country_id is not None:
            count_stmt = count_stmt.where(BESSUnit.country_id == country_id)
            stmt = stmt.where(BESSUnit.country_id == country_id)
        if stage is not None:
            count_stmt = count_stmt.where(BESSUnit.current_stage == stage)
            stmt = stmt.where(BESSUnit.current_stage == stage)
        if serial is not None:
            count_stmt = count_stmt.where(BESSUnit.serial_number.ilike(f"%{serial}%"))
            stmt = stmt.where(BESSUnit.serial_number.ilike(f"%{serial}%"))
        if customer_user_id is not None:
            count_stmt = count_stmt.where(BESSUnit.customer_user_id == customer_user_id)
            stmt = stmt.where(BESSUnit.customer_user_id == customer_user_id)

        total = await db.scalar(count_stmt)
        items = (
            await db.scalars(stmt.order_by(BESSUnit.id.desc()).offset((page - 1) * size).limit(size))
        ).all()
        return int(total or 0), list(items)

    async def create_stage_history(self, db: AsyncSession, history: StageHistory) -> StageHistory:
        db.add(history)
        await db.flush()
        return history

    async def create_audit_log(self, db: AsyncSession, log: AuditLog) -> AuditLog:
        db.add(log)
        await db.flush()
        return log

    async def list_history(self, db: AsyncSession, bess_unit_id: int) -> list[StageHistory]:
        stmt = (
            select(StageHistory)
            .where(StageHistory.bess_unit_id == bess_unit_id)
            .order_by(StageHistory.changed_at.desc(), StageHistory.id.desc())
        )
        return list((await db.scalars(stmt)).all())


bess_repository = BESSRepository()
