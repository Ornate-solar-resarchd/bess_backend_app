from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.shared.enums import BESSStage


class CommissioningRecordCreate(BaseModel):
    stage: BESSStage
    status: str = "PASS"
    notes: str | None = None


class CommissioningRecordRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    bess_unit_id: int
    stage: BESSStage
    status: str
    notes: str | None
    recorded_by_user_id: int
    created_at: datetime


class PaginatedCommissioningRecords(BaseModel):
    total: int
    items: list[CommissioningRecordRead]
    page: int
    size: int
