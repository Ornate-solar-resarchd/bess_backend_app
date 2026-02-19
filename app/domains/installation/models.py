from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum as SQLAlchemyEnum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared.base_model import Base, TimestampMixin
from app.shared.enums import BESSStage


class ChecklistTemplate(Base, TimestampMixin):
    __tablename__ = "checklist_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    stage: Mapped[BESSStage] = mapped_column(SQLAlchemyEnum(BESSStage), nullable=False, index=True)
    item_text: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    safety_warning: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_mandatory: Mapped[bool] = mapped_column(Boolean, default=True)
    requires_photo: Mapped[bool] = mapped_column(Boolean, default=False)
    order_index: Mapped[int] = mapped_column(Integer, default=0)


class ChecklistResponse(Base, TimestampMixin):
    __tablename__ = "checklist_responses"

    id: Mapped[int] = mapped_column(primary_key=True)
    bess_unit_id: Mapped[int] = mapped_column(ForeignKey("bess_units.id"), nullable=False, index=True)
    checklist_template_id: Mapped[int] = mapped_column(ForeignKey("checklist_templates.id"), nullable=False)
    template: Mapped[ChecklistTemplate] = relationship(lazy="selectin")
    stage: Mapped[BESSStage] = mapped_column(SQLAlchemyEnum(BESSStage), nullable=False)
    is_checked: Mapped[bool] = mapped_column(Boolean, default=False)
    checked_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    photo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
