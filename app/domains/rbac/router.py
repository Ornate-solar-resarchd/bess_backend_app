from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user, require_permission, require_role
from app.domains.auth.models import User
from app.domains.rbac.schemas import (
    AssignRoleRequest,
    PaginatedRoles,
    PaginatedUsers,
    RoleCreate,
    RoleRead,
    UserListRead,
)
from app.domains.rbac.service import assign_role_to_user, create_role, list_roles, list_users, remove_role_from_user

router = APIRouter(prefix="/admin", tags=["RBAC Admin"])


@router.get("/users", response_model=PaginatedUsers, dependencies=[Depends(require_permission("user:manage"))])
async def get_users(
    page: int = 1,
    size: int = 20,
    q: str | None = None,
    is_active: bool | None = None,
    db: AsyncSession = Depends(get_db),
) -> PaginatedUsers:
    total, items = await list_users(db, page, size, q, is_active)
    return PaginatedUsers(total=total, items=[UserListRead.model_validate(i) for i in items], page=page, size=size)


@router.get("/roles", response_model=PaginatedRoles, dependencies=[Depends(require_role("SUPER_ADMIN"))])
async def get_roles(
    page: int = 1,
    size: int = 20,
    db: AsyncSession = Depends(get_db),
) -> PaginatedRoles:
    total, items = await list_roles(db, page, size)
    return PaginatedRoles(total=total, items=[RoleRead.model_validate(i) for i in items], page=page, size=size)


@router.post("/roles", response_model=RoleRead, status_code=status.HTTP_201_CREATED)
async def create_role_endpoint(
    payload: RoleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("SUPER_ADMIN")),
) -> RoleRead:
    role = await create_role(db, payload, current_user.id)
    return RoleRead.model_validate(role)


@router.post("/users/{user_id}/roles", status_code=status.HTTP_204_NO_CONTENT)
async def assign_role_endpoint(
    user_id: int,
    payload: AssignRoleRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _: User = Depends(require_role("SUPER_ADMIN")),
) -> Response:
    await assign_role_to_user(db, user_id, payload.role_id, current_user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/users/{user_id}/roles/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_role_endpoint(
    user_id: int,
    role_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("SUPER_ADMIN")),
) -> Response:
    await remove_role_from_user(db, user_id, role_id, current_user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
