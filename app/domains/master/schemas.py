from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class CountryBase(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    code: str = Field(min_length=2, max_length=10)


class CountryCreate(CountryBase):
    pass


class CountryRead(CountryBase):
    model_config = ConfigDict(from_attributes=True)

    id: int


class CityCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    country_id: int


class NestedCountry(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class CityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    country: NestedCountry


class WarehouseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    city_id: int
    address: str | None = None


class NestedCity(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class WarehouseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    city: NestedCity
    address: str | None


class ProductModelCreate(BaseModel):
    model_number: str
    capacity_kwh: float
    description: str | None = None
    spec_fields: dict[str, str] | None = None


class ProductModelRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    model_number: str
    capacity_kwh: float
    description: str | None


class PaginatedCountries(BaseModel):
    total: int
    items: list[CountryRead]
    page: int
    size: int


class PaginatedCities(BaseModel):
    total: int
    items: list[CityRead]
    page: int
    size: int


class PaginatedWarehouses(BaseModel):
    total: int
    items: list[WarehouseRead]
    page: int
    size: int


class PaginatedProductModels(BaseModel):
    total: int
    items: list[ProductModelRead]
    page: int
    size: int
