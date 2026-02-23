from __future__ import annotations

from sqlalchemy import Enum as SQLAlchemyEnum, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import DateTime
from datetime import datetime

from app.shared.base_model import Base, TimestampMixin
from app.shared.enums import ShipmentStatus


class Shipment(Base, TimestampMixin):
    __tablename__ = "shipments"

    id: Mapped[int] = mapped_column(primary_key=True)
    shipment_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    origin_country_id: Mapped[int] = mapped_column(ForeignKey("countries.id"), nullable=False)
    destination_country_id: Mapped[int] = mapped_column(ForeignKey("countries.id"), nullable=False)
    expected_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[ShipmentStatus] = mapped_column(
        SQLAlchemyEnum(ShipmentStatus), default=ShipmentStatus.CREATED, nullable=False
    )


class ShipmentItem(Base, TimestampMixin):
    __tablename__ = "shipment_items"
    __table_args__ = (
        UniqueConstraint("shipment_id", "bess_unit_id", name="uq_shipment_item"),
        UniqueConstraint("bess_unit_id", name="uq_shipment_items_bess_unit_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    shipment_id: Mapped[int] = mapped_column(ForeignKey("shipments.id", ondelete="CASCADE"), nullable=False)
    shipment: Mapped[Shipment] = relationship(lazy="selectin")
    bess_unit_id: Mapped[int] = mapped_column(ForeignKey("bess_units.id"), nullable=False)
    order_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)


class ShipmentDocument(Base):
    __tablename__ = "shipment_documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    shipment_id: Mapped[int] = mapped_column(ForeignKey("shipments.id", ondelete="CASCADE"), nullable=False, index=True)
    shipment: Mapped[Shipment] = relationship(lazy="selectin")
    document_name: Mapped[str] = mapped_column(String(255), nullable=False)
    document_type: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    document_url: Mapped[str] = mapped_column(String(500), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    uploaded_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
