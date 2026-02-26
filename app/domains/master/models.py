from __future__ import annotations

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared.base_model import Base, TimestampMixin


class Country(Base, TimestampMixin):
    __tablename__ = "countries"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    code: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)


class City(Base, TimestampMixin):
    __tablename__ = "cities"
    __table_args__ = (UniqueConstraint("name", "country_id", name="uq_city_country"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    country_id: Mapped[int] = mapped_column(ForeignKey("countries.id"), nullable=False)
    country: Mapped[Country] = relationship(lazy="selectin")


class Warehouse(Base, TimestampMixin):
    __tablename__ = "warehouses"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    city_id: Mapped[int] = mapped_column(ForeignKey("cities.id"), nullable=False)
    city: Mapped[City] = relationship(lazy="selectin")
    address: Mapped[str | None] = mapped_column(Text, nullable=True)


class Site(Base, TimestampMixin):
    __tablename__ = "sites"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    country_id: Mapped[int] = mapped_column(ForeignKey("countries.id"), nullable=False)
    country: Mapped[Country] = relationship(lazy="selectin", foreign_keys=[country_id])
    city_id: Mapped[int] = mapped_column(ForeignKey("cities.id"), nullable=False)
    city: Mapped[City] = relationship(lazy="selectin", foreign_keys=[city_id])
    address: Mapped[str] = mapped_column(Text, nullable=False)
    latitude: Mapped[float | None] = mapped_column(nullable=True)
    longitude: Mapped[float | None] = mapped_column(nullable=True)


class ProductModel(Base, TimestampMixin):
    __tablename__ = "product_models"

    id: Mapped[int] = mapped_column(primary_key=True)
    model_number: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    capacity_kwh: Mapped[float] = mapped_column(nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
