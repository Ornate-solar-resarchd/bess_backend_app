from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import decode_token
from app.domains.auth.models import User
from app.domains.rbac.service import get_user_roles_permissions


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


@dataclass(slots=True)
class AuthContext:
    user: User
    roles: list[str]
    permissions: list[str]


async def get_auth_context(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> AuthContext:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(token)
    except ValueError as exc:
        raise credentials_exception from exc

    if payload.get("type") != "access":
        raise credentials_exception
    sub = payload.get("sub")
    if sub is None:
        raise credentials_exception

    user = await db.scalar(select(User).where(User.id == int(sub), User.is_active.is_(True)))
    if user is None:
        raise credentials_exception

    roles = list(payload.get("roles") or [])
    permissions = list(payload.get("permissions") or [])
    if not roles or not permissions:
        roles, permissions = await get_user_roles_permissions(db, user.id)

    return AuthContext(user=user, roles=roles, permissions=permissions)


async def get_current_user(context: AuthContext = Depends(get_auth_context)) -> User:
    return context.user


def require_permission(permission: str) -> Callable:
    async def checker(context: AuthContext = Depends(get_auth_context)) -> User:
        if permission not in context.permissions:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return context.user

    return checker


def require_role(*roles: str) -> Callable:
    role_set = set(roles)

    async def checker(context: AuthContext = Depends(get_auth_context)) -> User:
        if not role_set.intersection(context.roles):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        return context.user

    return checker
