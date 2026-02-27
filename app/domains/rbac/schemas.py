from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class PermissionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None


class RoleCreate(BaseModel):
    name: str
    description: str | None = None
    permission_ids: list[int] = []


class RoleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None


class AssignRoleRequest(BaseModel):
    role_id: int


class PaginatedRoles(BaseModel):
    total: int
    items: list[RoleRead]
    page: int
    size: int


class UserListRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str
    phone: str | None
    is_active: bool
    is_verified: bool


class PaginatedUsers(BaseModel):
    total: int
    items: list[UserListRead]
    page: int
    size: int
