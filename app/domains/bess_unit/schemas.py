from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.shared.enums import BESSStage


class NestedNamed(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class NestedProductModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    model_number: str
    capacity_kwh: float


class BESSUnitCreate(BaseModel):
    serial_number: str | None = None
    existing_qr_code_url: str | None = None
    regenerate_qr_png: bool = True
    product_model_id: int
    country_id: int
    city_id: int
    warehouse_id: int | None = None
    site_address: str | None = None
    site_latitude: float | None = None
    site_longitude: float | None = None
    customer_user_id: int | None = None
    manufactured_date: datetime | None = None


class BESSUnitRegisterFromQR(BaseModel):
    qr_raw_data: str
    serial_number_override: str | None = None
    existing_qr_code_url: str | None = None
    product_model_id: int | None = None
    country_id: int
    city_id: int
    warehouse_id: int | None = None
    site_address: str | None = None
    site_latitude: float | None = None
    site_longitude: float | None = None
    customer_user_id: int | None = None
    manufactured_date: datetime | None = None


class QRParseRequest(BaseModel):
    qr_raw_data: str


class QRParseResponse(BaseModel):
    serial_number: str | None
    model_number: str | None
    manufactured_date: datetime | None
    normalized_fields: dict[str, str]
    can_register: bool
    message: str


class BESSUnitUpdate(BaseModel):
    country_id: int | None = None
    city_id: int | None = None
    warehouse_id: int | None = None
    site_address: str | None = None
    site_latitude: float | None = None
    site_longitude: float | None = None
    customer_user_id: int | None = None


class BESSUnitRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    serial_number: str
    qr_code_url: str | None
    current_stage: BESSStage
    is_active: bool
    product_model: NestedProductModel
    country: NestedNamed
    city: NestedNamed
    warehouse: NestedNamed | None
    site_address: str | None
    site_latitude: float | None
    site_longitude: float | None
    customer_user_id: int | None
    manufactured_date: datetime | None
    created_at: datetime
    updated_at: datetime


class StageTransitionRequest(BaseModel):
    to_stage: BESSStage
    notes: str | None = None


class StageHistoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    bess_unit_id: int
    from_stage: BESSStage
    to_stage: BESSStage
    changed_by_user_id: int
    changed_at: datetime
    notes: str | None


class PaginatedBESSUnits(BaseModel):
    total: int
    items: list[BESSUnitRead]
    page: int
    size: int


class ChecklistScanItem(BaseModel):
    item_text: str
    is_mandatory: bool
    is_checked: bool
    requires_photo: bool


class ScanEngineer(BaseModel):
    name: str
    phone_masked: str | None


class ScanResponse(BaseModel):
    bess_unit: BESSUnitRead
    product_specs: NestedProductModel
    current_stage: BESSStage
    assigned_engineer: ScanEngineer | None
    checklist: list[ChecklistScanItem]
    stage_instructions: str
