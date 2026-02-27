from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.auth.models import User
from app.domains.bess_unit.models import AuditLog
from app.domains.bess_unit.repository import bess_repository
from app.domains.rbac.models import Role
from app.domains.rbac.repository import rbac_repository
from app.domains.rbac.schemas import RoleCreate
from app.shared.acid import atomic
from app.shared.exceptions import APIConflictException, APINotFoundException


async def get_user_roles_permissions(db: AsyncSession, user_id: int) -> tuple[list[str], list[str]]:
    role_ids, role_names = await rbac_repository.get_user_role_names_and_ids(db, user_id)
    permissions = await rbac_repository.get_role_permissions(db, role_ids)
    return role_names, permissions


async def list_roles(db: AsyncSession, page: int, size: int):
    return await rbac_repository.list_roles(db, page, size)


async def list_users(
    db: AsyncSession,
    page: int,
    size: int,
    query: str | None = None,
    is_active: bool | None = None,
):
    return await rbac_repository.list_users(db, page, size, query, is_active)


async def create_role(db: AsyncSession, payload: RoleCreate, actor_user_id: int | None):
    duplicate = await db.scalar(select(Role).where(Role.name == payload.name))
    if duplicate is not None:
        raise APIConflictException("Role already exists")
    async with atomic(db) as session:
        role = await rbac_repository.create_role(
            session,
            name=payload.name,
            description=payload.description,
            permission_ids=payload.permission_ids,
        )
        await bess_repository.create_audit_log(
            session,
            AuditLog(
                user_id=actor_user_id,
                action="RBAC_ROLE_CREATE",
                entity_type="Role",
                entity_id=role.id,
                payload_json={"name": role.name},
            ),
        )
    return role


async def assign_role_to_user(
    db: AsyncSession, user_id: int, role_id: int, assigned_by_user_id: int | None
):
    user = await db.get(User, user_id)
    if not user:
        raise APINotFoundException("User not found")
    async with atomic(db) as session:
        row = await rbac_repository.assign_role(session, user_id, role_id, assigned_by_user_id)
        await bess_repository.create_audit_log(
            session,
            AuditLog(
                user_id=assigned_by_user_id,
                action="RBAC_ROLE_ASSIGN",
                entity_type="UserRole",
                entity_id=user_id,
                payload_json={"user_id": user_id, "role_id": role_id},
            ),
        )
        return row


async def remove_role_from_user(
    db: AsyncSession,
    user_id: int,
    role_id: int,
    actor_user_id: int | None,
) -> None:
    async with atomic(db) as session:
        deleted = await rbac_repository.remove_role(session, user_id, role_id)
        if not deleted:
            raise APINotFoundException("User role assignment not found")
        await bess_repository.create_audit_log(
            session,
            AuditLog(
                user_id=actor_user_id,
                action="RBAC_ROLE_REMOVE",
                entity_type="UserRole",
                entity_id=user_id,
                payload_json={"user_id": user_id, "role_id": role_id},
            ),
        )
