from __future__ import annotations

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.commissioning.models import CommissioningRecord


class CommissioningRepository:
    async def create(self, db: AsyncSession, record: CommissioningRecord) -> CommissioningRecord:
        db.add(record)
        await db.flush()
        return record

    async def list_by_bess(
        self,
        db: AsyncSession,
        bess_unit_id: int,
        page: int,
        size: int,
    ) -> tuple[int, list[CommissioningRecord]]:
        total = await db.scalar(
            select(func.count(CommissioningRecord.id)).where(CommissioningRecord.bess_unit_id == bess_unit_id)
        )
        stmt: Select[tuple[CommissioningRecord]] = (
            select(CommissioningRecord)
            .where(CommissioningRecord.bess_unit_id == bess_unit_id)
            .order_by(CommissioningRecord.id.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        items = (await db.scalars(stmt)).all()
        return int(total or 0), list(items)


commissioning_repository = CommissioningRepository()
