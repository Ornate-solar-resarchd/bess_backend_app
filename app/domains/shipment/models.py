from __future__ import annotations

from sqlalchemy import Enum as SQLAlchemyEnum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared.base_model import Base, TimestampMixin
from app.shared.enums import ShipmentStatus


class Shipment(Base, TimestampMixin):
    __tablename__ = "shipments"

    id: Mapped[int] = mapped_column(primary_key=True)
    shipment_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    origin_country_id: Mapped[int] = mapped_column(ForeignKey("countries.id"), nullable=False)
    destination_country_id: Mapped[int] = mapped_column(ForeignKey("countries.id"), nullable=False)
    status: Mapped[ShipmentStatus] = mapped_column(
        SQLAlchemyEnum(ShipmentStatus), default=ShipmentStatus.CREATED, nullable=False
    )


class ShipmentItem(Base, TimestampMixin):
    __tablename__ = "shipment_items"
    __table_args__ = (UniqueConstraint("shipment_id", "bess_unit_id", name="uq_shipment_item"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    shipment_id: Mapped[int] = mapped_column(ForeignKey("shipments.id", ondelete="CASCADE"), nullable=False)
    shipment: Mapped[Shipment] = relationship(lazy="selectin")
    bess_unit_id: Mapped[int] = mapped_column(ForeignKey("bess_units.id"), nullable=False)
