from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.shared.enums import BESSStage


class ChecklistItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    checklist_template_id: int
    stage: BESSStage
    item_text: str
    description: str | None
    safety_warning: str | None
    is_mandatory: bool
    requires_photo: bool
    order_index: int
    is_checked: bool
    checked_by_user_id: int | None
    checked_at: datetime | None
    notes: str | None
    photo_url: str | None


class ChecklistUpdateRequest(BaseModel):
    is_checked: bool
    notes: str | None = None
    photo_url: str | None = None


class ChecklistValidationResponse(BaseModel):
    all_complete: bool
    pending_items: list[str]
