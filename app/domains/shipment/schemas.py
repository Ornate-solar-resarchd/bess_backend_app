from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from app.shared.enums import ShipmentStatus


class ShipmentCreate(BaseModel):
    shipment_code: str
    origin_country_id: int
    destination_country_id: int


class ShipmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    shipment_code: str
    origin_country_id: int
    destination_country_id: int
    status: ShipmentStatus


class ShipmentItemAssign(BaseModel):
    bess_unit_id: int
    order_id: str


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
