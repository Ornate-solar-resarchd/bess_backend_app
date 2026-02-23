from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict
from pydantic import Field

from app.shared.enums import ShipmentStatus


class ShipmentCreate(BaseModel):
    shipment_code: str
    origin_country_id: int
    destination_country_id: int
    expected_quantity: int = Field(default=1, ge=1)


class ShipmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    shipment_code: str
    origin_country_id: int
    destination_country_id: int
    expected_quantity: int
    status: ShipmentStatus


class ShipmentItemAssign(BaseModel):
    bess_unit_id: int
    order_id: str


class ShipmentBulkItemAssign(BaseModel):
    items: list[ShipmentItemAssign]


class ShipmentStatusUpdate(BaseModel):
    status: ShipmentStatus


class PaginatedShipments(BaseModel):
    total: int
    items: list[ShipmentRead]
    page: int
    size: int


class ShipmentItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    shipment_id: int
    bess_unit_id: int
    order_id: str | None


class PaginatedShipmentItems(BaseModel):
    total: int
    items: list[ShipmentItemRead]
    page: int
    size: int


class ShipmentDocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    shipment_id: int
    document_name: str
    document_type: str | None
    document_url: str
    notes: str | None
    uploaded_by_user_id: int | None
    uploaded_at: datetime


class PaginatedShipmentDocuments(BaseModel):
    total: int
    items: list[ShipmentDocumentRead]
    page: int
    size: int


class ShipmentDetailRead(BaseModel):
    shipment: ShipmentRead
    units_total: int
    units: list[ShipmentItemRead]
    documents_total: int
    documents: list[ShipmentDocumentRead]
