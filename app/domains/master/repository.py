from __future__ import annotations

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.master.models import City, Country, ProductModel, Warehouse


class MasterRepository:
    async def list_countries(self, db: AsyncSession, page: int, size: int) -> tuple[int, list[Country]]:
        total = await db.scalar(select(func.count(Country.id)))
        stmt: Select[tuple[Country]] = select(Country).order_by(Country.name).offset((page - 1) * size).limit(size)
        items = (await db.scalars(stmt)).all()
        return int(total or 0), list(items)

    async def create_country(self, db: AsyncSession, name: str, code: str) -> Country:
        obj = Country(name=name, code=code)
        db.add(obj)
        await db.flush()
        return obj

    async def list_cities(
        self, db: AsyncSession, page: int, size: int, country_id: int | None
    ) -> tuple[int, list[City]]:
        count_stmt = select(func.count(City.id))
        stmt: Select[tuple[City]] = select(City)
        if country_id is not None:
            count_stmt = count_stmt.where(City.country_id == country_id)
            stmt = stmt.where(City.country_id == country_id)
        total = await db.scalar(count_stmt)
        items = (
            await db.scalars(stmt.order_by(City.name).offset((page - 1) * size).limit(size))
        ).all()
        return int(total or 0), list(items)

    async def create_city(self, db: AsyncSession, name: str, country_id: int) -> City:
        obj = City(name=name, country_id=country_id)
        db.add(obj)
        await db.flush()
        await db.refresh(obj)
        return obj

    async def list_warehouses(
        self, db: AsyncSession, page: int, size: int, city_id: int | None
    ) -> tuple[int, list[Warehouse]]:
        count_stmt = select(func.count(Warehouse.id))
        stmt: Select[tuple[Warehouse]] = select(Warehouse)
        if city_id is not None:
            count_stmt = count_stmt.where(Warehouse.city_id == city_id)
            stmt = stmt.where(Warehouse.city_id == city_id)
        total = await db.scalar(count_stmt)
        items = (
            await db.scalars(stmt.order_by(Warehouse.id).offset((page - 1) * size).limit(size))
        ).all()
        return int(total or 0), list(items)

    async def create_warehouse(self, db: AsyncSession, name: str, city_id: int, address: str | None) -> Warehouse:
        obj = Warehouse(name=name, city_id=city_id, address=address)
        db.add(obj)
        await db.flush()
        await db.refresh(obj)
        return obj

    async def list_product_models(self, db: AsyncSession, page: int, size: int) -> tuple[int, list[ProductModel]]:
        total = await db.scalar(select(func.count(ProductModel.id)))
        items = (
            await db.scalars(
                select(ProductModel)
                .order_by(ProductModel.model_number)
                .offset((page - 1) * size)
                .limit(size)
            )
        ).all()
        return int(total or 0), list(items)

    async def create_product_model(
        self,
        db: AsyncSession,
        model_number: str,
        capacity_kwh: float,
        description: str | None,
    ) -> ProductModel:
        obj = ProductModel(
            model_number=model_number,
            capacity_kwh=capacity_kwh,
            description=description,
        )
        db.add(obj)
        await db.flush()
        return obj


master_repository = MasterRepository()
