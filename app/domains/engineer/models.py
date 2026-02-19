from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum as SQLAlchemyEnum,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared.base_model import Base, TimestampMixin
from app.shared.enums import AssignmentStatus, BESSStage, Specialization


class Engineer(Base, TimestampMixin):
    __tablename__ = "engineers"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, nullable=False)
    user: Mapped["User"] = relationship(lazy="selectin")
    employee_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    specialization: Mapped[Specialization] = mapped_column(SQLAlchemyEnum(Specialization), nullable=False)
    city_id: Mapped[int] = mapped_column(ForeignKey("cities.id"), nullable=False)
    city: Mapped["City"] = relationship(lazy="selectin")
    country_id: Mapped[int] = mapped_column(ForeignKey("countries.id"), nullable=False)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True)
    max_concurrent_assignments: Mapped[int] = mapped_column(Integer, default=1)
    certifications: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class SiteAssignment(Base, TimestampMixin):
    __tablename__ = "site_assignments"

    id: Mapped[int] = mapped_column(primary_key=True)
    bess_unit_id: Mapped[int] = mapped_column(ForeignKey("bess_units.id"), nullable=False, index=True)
    engineer_id: Mapped[int] = mapped_column(ForeignKey("engineers.id"), nullable=False)
    engineer: Mapped[Engineer] = relationship(lazy="selectin")
    assigned_stage: Mapped[BESSStage] = mapped_column(SQLAlchemyEnum(BESSStage), nullable=False)
    status: Mapped[AssignmentStatus] = mapped_column(
        SQLAlchemyEnum(AssignmentStatus), default=AssignmentStatus.PENDING
    )
    assigned_by: Mapped[str] = mapped_column(String(10), default="AUTO")
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
