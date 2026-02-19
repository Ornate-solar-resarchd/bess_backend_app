from __future__ import annotations

from sqlalchemy import Enum as SQLAlchemyEnum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.base_model import Base, TimestampMixin
from app.shared.enums import BESSStage


class CommissioningRecord(Base, TimestampMixin):
    __tablename__ = "commissioning_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    bess_unit_id: Mapped[int] = mapped_column(ForeignKey("bess_units.id"), nullable=False, index=True)
    stage: Mapped[BESSStage] = mapped_column(SQLAlchemyEnum(BESSStage), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="PASS", nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    recorded_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
