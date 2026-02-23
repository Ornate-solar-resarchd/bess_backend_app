from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum as SQLAlchemyEnum, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared.base_model import Base, SoftDeleteMixin, TimestampMixin
from app.shared.enums import BESSStage


class BESSUnit(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "bess_units"

    id: Mapped[int] = mapped_column(primary_key=True)
    serial_number: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    qr_code_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    product_model_id: Mapped[int] = mapped_column(ForeignKey("product_models.id"), nullable=False)
    product_model: Mapped["ProductModel"] = relationship(lazy="selectin")

    current_stage: Mapped[BESSStage] = mapped_column(
        SQLAlchemyEnum(BESSStage), default=BESSStage.FACTORY_REGISTERED, nullable=False
    )

    country_id: Mapped[int] = mapped_column(ForeignKey("countries.id"), nullable=False)
    country: Mapped["Country"] = relationship(lazy="selectin", foreign_keys=[country_id])

    city_id: Mapped[int] = mapped_column(ForeignKey("cities.id"), nullable=False)
    city: Mapped["City"] = relationship(lazy="selectin", foreign_keys=[city_id])

    warehouse_id: Mapped[int | None] = mapped_column(ForeignKey("warehouses.id"), nullable=True)
    warehouse: Mapped["Warehouse | None"] = relationship(lazy="selectin")

    site_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    site_latitude: Mapped[float | None] = mapped_column(nullable=True)
    site_longitude: Mapped[float | None] = mapped_column(nullable=True)

    customer_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    installed_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    manufactured_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class StageHistory(Base):
    __tablename__ = "stage_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    bess_unit_id: Mapped[int] = mapped_column(ForeignKey("bess_units.id"), nullable=False, index=True)
    from_stage: Mapped[BESSStage] = mapped_column(SQLAlchemyEnum(BESSStage), nullable=False)
    to_stage: Mapped[BESSStage] = mapped_column(SQLAlchemyEnum(BESSStage), nullable=False)
    changed_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[int] = mapped_column(nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(50), nullable=True)
    payload_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class StageCertificate(Base):
    __tablename__ = "stage_certificates"

    id: Mapped[int] = mapped_column(primary_key=True)
    bess_unit_id: Mapped[int] = mapped_column(ForeignKey("bess_units.id"), nullable=False, index=True)
    stage: Mapped[BESSStage] = mapped_column(SQLAlchemyEnum(BESSStage), nullable=False, index=True)
    certificate_name: Mapped[str] = mapped_column(String(200), nullable=False)
    certificate_url: Mapped[str] = mapped_column(String(500), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    uploaded_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
