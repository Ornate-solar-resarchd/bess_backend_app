from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import require_permission
from app.domains.auth.models import User
from app.domains.master import service
from app.domains.master.schemas import (
    CityCreate,
    CityRead,
    CountryCreate,
    CountryRead,
    PaginatedCities,
    PaginatedCountries,
    PaginatedProductModels,
    PaginatedSites,
    PaginatedWarehouses,
    ProductModelCreate,
    ProductModelRead,
    SiteCreate,
    SiteRead,
    WarehouseCreate,
    WarehouseRead,
)

router = APIRouter(prefix="/master", tags=["Master"])


@router.get("/countries", response_model=PaginatedCountries, dependencies=[Depends(require_permission("master:read"))])
async def get_countries(page: int = 1, size: int = 20, db: AsyncSession = Depends(get_db)) -> PaginatedCountries:
    total, items = await service.list_countries(db, page, size)
    return PaginatedCountries(total=total, items=[CountryRead.model_validate(i) for i in items], page=page, size=size)


@router.post(
    "/countries",
    response_model=CountryRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_country(
    payload: CountryCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("master:write")),
) -> CountryRead:
    obj = await service.create_country(db, payload, current_user)
    return CountryRead.model_validate(obj)


@router.get("/cities", response_model=PaginatedCities, dependencies=[Depends(require_permission("master:read"))])
async def get_cities(
    country_id: int | None = None,
    page: int = 1,
    size: int = 20,
    db: AsyncSession = Depends(get_db),
) -> PaginatedCities:
    total, items = await service.list_cities(db, page, size, country_id)
    return PaginatedCities(total=total, items=[CityRead.model_validate(i) for i in items], page=page, size=size)


@router.post(
    "/cities",
    response_model=CityRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_city(
    payload: CityCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("master:write")),
) -> CityRead:
    obj = await service.create_city(db, payload, current_user)
    return CityRead.model_validate(obj)


@router.get("/warehouses", response_model=PaginatedWarehouses, dependencies=[Depends(require_permission("master:read"))])
async def get_warehouses(
    city_id: int | None = None,
    page: int = 1,
    size: int = 20,
    db: AsyncSession = Depends(get_db),
) -> PaginatedWarehouses:
    total, items = await service.list_warehouses(db, page, size, city_id)
    return PaginatedWarehouses(
        total=total,
        items=[WarehouseRead.model_validate(i) for i in items],
        page=page,
        size=size,
    )


@router.post(
    "/warehouses",
    response_model=WarehouseRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_warehouse(
    payload: WarehouseCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("master:write")),
) -> WarehouseRead:
    obj = await service.create_warehouse(db, payload, current_user)
    return WarehouseRead.model_validate(obj)


@router.get("/sites", response_model=PaginatedSites, dependencies=[Depends(require_permission("master:read"))])
async def get_sites(
    city_id: int | None = None,
    country_id: int | None = None,
    page: int = 1,
    size: int = 20,
    db: AsyncSession = Depends(get_db),
) -> PaginatedSites:
    total, items = await service.list_sites(db, page, size, city_id, country_id)
    return PaginatedSites(
        total=total,
        items=[SiteRead.model_validate(i) for i in items],
        page=page,
        size=size,
    )


@router.post(
    "/sites",
    response_model=SiteRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_site(
    payload: SiteCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("master:write")),
) -> SiteRead:
    obj = await service.create_site(db, payload, current_user)
    return SiteRead.model_validate(obj)


@router.get(
    "/product-models",
    response_model=PaginatedProductModels,
    dependencies=[Depends(require_permission("master:read"))],
)
async def get_product_models(
    page: int = 1,
    size: int = 20,
    db: AsyncSession = Depends(get_db),
) -> PaginatedProductModels:
    total, items = await service.list_product_models(db, page, size)
    return PaginatedProductModels(
        total=total,
        items=[ProductModelRead.model_validate(i) for i in items],
        page=page,
        size=size,
    )


@router.post(
    "/product-models",
    response_model=ProductModelRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_product_model(
    payload: ProductModelCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("master:write")),
) -> ProductModelRead:
    obj = await service.create_product_model(db, payload, current_user)
    return ProductModelRead.model_validate(obj)
