from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.bess_unit.models import BESSUnit


async def stage_distribution(db: AsyncSession, page: int, size: int) -> tuple[int, list[tuple[object, int]]]:
    grouped = (
        await db.execute(
            select(BESSUnit.current_stage, func.count(BESSUnit.id))
            .where(BESSUnit.is_deleted.is_(False))
            .group_by(BESSUnit.current_stage)
            .order_by(BESSUnit.current_stage)
        )
    ).all()
    total = len(grouped)
    start = (page - 1) * size
    end = start + size
    return total, grouped[start:end]
