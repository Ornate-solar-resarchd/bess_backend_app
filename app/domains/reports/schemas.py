from __future__ import annotations

from pydantic import BaseModel

from app.shared.enums import BESSStage


class StageReportItem(BaseModel):
    stage: BESSStage
    total_units: int


class ReportsResponse(BaseModel):
    total: int
    items: list[StageReportItem]
    page: int
    size: int
