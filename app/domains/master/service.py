from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.auth.models import User
from app.domains.bess_unit.models import AuditLog
from app.domains.bess_unit.repository import bess_repository
from app.domains.master.models import City, Country, ProductModel, Site
from app.domains.master.normalization import build_product_description, normalize_hess_to_uess
from app.domains.master.repository import master_repository
from app.domains.master.schemas import CityCreate, CountryCreate, ProductModelCreate, SiteCreate, WarehouseCreate
from app.shared.acid import atomic
from app.shared.exceptions import APIConflictException, APINotFoundException


async def list_countries(db: AsyncSession, page: int, size: int):
    return await master_repository.list_countries(db, page, size)


async def create_country(db: AsyncSession, payload: CountryCreate, current_user: User):
    duplicate = await db.scalar(select(Country).where((Country.name == payload.name) | (Country.code == payload.code)))
    if duplicate:
        raise APIConflictException("Country with same name/code already exists")
    async with atomic(db) as session:
        obj = await master_repository.create_country(session, payload.name, payload.code)
        await bess_repository.create_audit_log(
            session,
            AuditLog(
                user_id=current_user.id,
                action="MASTER_COUNTRY_CREATE",
                entity_type="Country",
                entity_id=obj.id,
                payload_json={"name": obj.name, "code": obj.code},
            ),
        )
        return obj


async def list_cities(db: AsyncSession, page: int, size: int, country_id: int | None):
    return await master_repository.list_cities(db, page, size, country_id)


async def create_city(db: AsyncSession, payload: CityCreate, current_user: User):
    country_exists = await db.get(Country, payload.country_id)
    if not country_exists:
        raise APINotFoundException("Country not found")
    duplicate = await db.scalar(
        select(City).where(City.name == payload.name, City.country_id == payload.country_id)
    )
    if duplicate:
        raise APIConflictException("City already exists for country")
    async with atomic(db) as session:
        obj = await master_repository.create_city(session, payload.name, payload.country_id)
        await bess_repository.create_audit_log(
            session,
            AuditLog(
                user_id=current_user.id,
                action="MASTER_CITY_CREATE",
                entity_type="City",
                entity_id=obj.id,
                payload_json={"name": obj.name, "country_id": obj.country_id},
            ),
        )
        return obj


async def list_warehouses(db: AsyncSession, page: int, size: int, city_id: int | None):
    return await master_repository.list_warehouses(db, page, size, city_id)


async def create_warehouse(db: AsyncSession, payload: WarehouseCreate, current_user: User):
    city = await db.get(City, payload.city_id)
    if not city:
        raise APINotFoundException("City not found")
    async with atomic(db) as session:
        obj = await master_repository.create_warehouse(session, payload.name, payload.city_id, payload.address)
        await bess_repository.create_audit_log(
            session,
            AuditLog(
                user_id=current_user.id,
                action="MASTER_WAREHOUSE_CREATE",
                entity_type="Warehouse",
                entity_id=obj.id,
                payload_json={"name": obj.name, "city_id": obj.city_id},
            ),
        )
        return obj


async def list_sites(
    db: AsyncSession,
    page: int,
    size: int,
    city_id: int | None,
    country_id: int | None,
):
    return await master_repository.list_sites(db, page, size, city_id, country_id)


async def create_site(db: AsyncSession, payload: SiteCreate, current_user: User):
    country = await db.get(Country, payload.country_id)
    if not country:
        raise APINotFoundException("Country not found")
    city = await db.get(City, payload.city_id)
    if not city:
        raise APINotFoundException("City not found")
    if city.country_id != payload.country_id:
        raise APIConflictException("Selected city does not belong to selected country")

    duplicate = await db.scalar(
        select(Site).where(
            Site.name == payload.name.strip(),
            Site.city_id == payload.city_id,
            Site.address == payload.address.strip(),
        )
    )
    if duplicate:
        raise APIConflictException("Site already exists for city/address")

    async with atomic(db) as session:
        obj = await master_repository.create_site(
            session,
            name=payload.name.strip(),
            country_id=payload.country_id,
            city_id=payload.city_id,
            address=payload.address.strip(),
            latitude=payload.latitude,
            longitude=payload.longitude,
        )
        await bess_repository.create_audit_log(
            session,
            AuditLog(
                user_id=current_user.id,
                action="MASTER_SITE_CREATE",
                entity_type="Site",
                entity_id=obj.id,
                payload_json={"name": obj.name, "city_id": obj.city_id, "country_id": obj.country_id},
            ),
        )
        return obj


async def list_product_models(db: AsyncSession, page: int, size: int):
    return await master_repository.list_product_models(db, page, size)


async def create_product_model(db: AsyncSession, payload: ProductModelCreate, current_user: User):
    normalized_model_number = normalize_hess_to_uess(payload.model_number.strip().upper())
    duplicate = await db.scalar(
        select(ProductModel).where(ProductModel.model_number.ilike(normalized_model_number))
    )
    if duplicate:
        raise APIConflictException("Product model already exists")
    normalized_description = build_product_description(payload.description, payload.spec_fields)
    async with atomic(db) as session:
        obj = await master_repository.create_product_model(
            session,
            model_number=normalized_model_number,
            capacity_kwh=payload.capacity_kwh,
            description=normalized_description,
        )
        await bess_repository.create_audit_log(
            session,
            AuditLog(
                user_id=current_user.id,
                action="MASTER_PRODUCT_MODEL_CREATE",
                entity_type="ProductModel",
                entity_id=obj.id,
                payload_json={
                    "model_number": obj.model_number,
                    "capacity_kwh": obj.capacity_kwh,
                },
            ),
        )
        return obj
