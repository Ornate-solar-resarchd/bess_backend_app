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


class HandoverBrandingRead(BaseModel):
    template_name: str | None
    template_version: str | None
    checklist_logo_dark: str | None
    checklist_logo_light: str | None
    brand_logo: str | None


class HandoverBESSDetailsRead(BaseModel):
    bess_unit_id: int
    serial_number: str
    model_number: str | None
    model_capacity_kwh: float | None
    current_stage: BESSStage
    manufactured_date: datetime | None
    country: str | None
    city: str | None
    warehouse: str | None
    site_address: str | None
    site_latitude: float | None
    site_longitude: float | None
    customer_user_id: int | None


class HandoverSignatureRead(BaseModel):
    role: str
    item_text: str
    signed_by_user_id: int | None
    signed_by_name: str
    signed_at: datetime | None
    photo_url: str


class HandoverChecklistItemRead(BaseModel):
    checklist_template_id: int
    item_text: str
    description: str | None
    safety_warning: str | None
    is_mandatory: bool
    requires_photo: bool
    is_checked: bool
    checked_by_user_id: int | None
    checked_at: datetime | None
    notes: str | None
    photo_url: str | None
    order_index: int


class HandoverChecklistStageRead(BaseModel):
    stage: BESSStage
    total_items: int
    completed_items: int
    items: list[HandoverChecklistItemRead]


class HandoverDocumentDataRead(BaseModel):
    generated_at: datetime
    branding: HandoverBrandingRead
    bess: HandoverBESSDetailsRead
    signatures: list[HandoverSignatureRead]
    stages: list[HandoverChecklistStageRead]
