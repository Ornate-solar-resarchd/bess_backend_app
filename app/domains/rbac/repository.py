from __future__ import annotations

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.auth.models import User
from app.domains.rbac.models import Permission, Role, RolePermission, UserRole


class RBACRepository:
    async def list_users(
        self,
        db: AsyncSession,
        page: int,
        size: int,
        query: str | None = None,
        is_active: bool | None = None,
    ) -> tuple[int, list[User]]:
        count_stmt = select(func.count(User.id))
        stmt: Select[tuple[User]] = select(User)

        if is_active is not None:
            count_stmt = count_stmt.where(User.is_active.is_(is_active))
            stmt = stmt.where(User.is_active.is_(is_active))

        normalized_query = (query or "").strip()
        if normalized_query:
            like_value = f"%{normalized_query}%"
            search_filter = User.full_name.ilike(like_value) | User.email.ilike(like_value) | User.phone.ilike(
                like_value
            )
            count_stmt = count_stmt.where(search_filter)
            stmt = stmt.where(search_filter)

        total = await db.scalar(count_stmt)
        items = (
            await db.scalars(stmt.order_by(User.id.asc()).offset((page - 1) * size).limit(size))
        ).all()
        return int(total or 0), list(items)

    async def list_roles(self, db: AsyncSession, page: int, size: int) -> tuple[int, list[Role]]:
        total = await db.scalar(select(func.count(Role.id)))
        stmt: Select[tuple[Role]] = select(Role).offset((page - 1) * size).limit(size).order_by(Role.id)
        items = (await db.scalars(stmt)).all()
        return int(total or 0), list(items)

    async def create_role(
        self, db: AsyncSession, name: str, description: str | None, permission_ids: list[int]
    ) -> Role:
        role = Role(name=name, description=description)
        db.add(role)
        await db.flush()
        for permission_id in permission_ids:
            db.add(RolePermission(role_id=role.id, permission_id=permission_id))
        await db.flush()
        return role

    async def assign_role(
        self,
        db: AsyncSession,
        user_id: int,
        role_id: int,
        assigned_by_user_id: int | None,
    ) -> UserRole:
        user_role = UserRole(user_id=user_id, role_id=role_id, assigned_by_user_id=assigned_by_user_id)
        db.add(user_role)
        await db.flush()
        return user_role

    async def remove_role(self, db: AsyncSession, user_id: int, role_id: int) -> int:
        stmt = select(UserRole).where(UserRole.user_id == user_id, UserRole.role_id == role_id)
        entity = await db.scalar(stmt)
        if not entity:
            return 0
        await db.delete(entity)
        await db.flush()
        return 1

    async def get_role_permissions(self, db: AsyncSession, role_ids: list[int]) -> list[str]:
        if not role_ids:
            return []
        stmt = (
            select(Permission.name)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .where(RolePermission.role_id.in_(role_ids))
            .distinct()
        )
        rows = (await db.execute(stmt)).all()
        return [name for (name,) in rows]

    async def get_user_role_names_and_ids(self, db: AsyncSession, user_id: int) -> tuple[list[int], list[str]]:
        stmt = (
            select(Role.id, Role.name)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user_id)
            .distinct()
        )
        rows = (await db.execute(stmt)).all()
        role_ids = [role_id for role_id, _ in rows]
        role_names = [name for _, name in rows]
        return role_ids, role_names


rbac_repository = RBACRepository()
