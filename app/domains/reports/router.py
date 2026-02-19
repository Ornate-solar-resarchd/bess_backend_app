from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import require_permission
from app.domains.auth.models import User
from app.domains.reports.schemas import ReportsResponse, StageReportItem
from app.domains.reports.service import stage_distribution

router = APIRouter(prefix="/reports", tags=["Reports"])


@router.get("/", response_model=ReportsResponse)
async def get_reports(
    page: int = 1,
    size: int = 20,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission("report:view")),
) -> ReportsResponse:
    total, rows = await stage_distribution(db, page, size)
    return ReportsResponse(
        total=total,
        items=[StageReportItem(stage=stage, total_units=count) for stage, count in rows],
        page=page,
        size=size,
    )
