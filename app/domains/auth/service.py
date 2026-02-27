from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_password_hash,
    verify_password,
)
from app.domains.bess_unit.models import AuditLog
from app.domains.bess_unit.repository import bess_repository
from app.domains.auth.models import User
from app.domains.auth.schemas import LoginRequest, LoginResponse, RegisterRequest, TokenResponse, UserRead
from app.domains.rbac.models import Role, UserRole
from app.domains.rbac.service import get_user_roles_permissions
from app.shared.acid import atomic
from app.shared.exceptions import APIConflictException, APIValidationException


async def register_user(db: AsyncSession, payload: RegisterRequest) -> User:
    existing = await db.scalar(select(User).where(User.email == payload.email))
    if existing:
        raise APIConflictException("Email is already registered")

    async with atomic(db) as session:
        user = User(
            email=payload.email.lower(),
            hashed_password=get_password_hash(payload.password),
            full_name=payload.full_name,
            phone=payload.phone,
        )
        session.add(user)
        await session.flush()

        customer_role = await session.scalar(select(Role).where(Role.name == "CUSTOMER"))
        if customer_role:
            session.add(UserRole(user_id=user.id, role_id=customer_role.id, assigned_by_user_id=None))
        await bess_repository.create_audit_log(
            session,
            AuditLog(
                user_id=user.id,
                action="AUTH_REGISTER",
                entity_type="User",
                entity_id=user.id,
                payload_json={"email": user.email},
            ),
        )

    return user


async def authenticate(db: AsyncSession, payload: LoginRequest) -> User:
    user = await db.scalar(select(User).where(User.email == payload.email.lower()))
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise APIValidationException("Invalid email or password")
    if not user.is_active:
        raise APIValidationException("User is inactive")
    return user


async def issue_tokens(db: AsyncSession, user: User) -> TokenResponse:
    roles, permissions = await get_user_roles_permissions(db, user.id)
    base_payload: dict[str, object] = {
        "sub": str(user.id),
        "email": user.email,
        "roles": roles,
        "permissions": permissions,
    }
    return TokenResponse(
        access_token=create_access_token(base_payload),
        refresh_token=create_refresh_token(base_payload),
    )


async def issue_login_response(db: AsyncSession, user: User) -> LoginResponse:
    roles, permissions = await get_user_roles_permissions(db, user.id)
    base_payload: dict[str, object] = {
        "sub": str(user.id),
        "email": user.email,
        "roles": roles,
        "permissions": permissions,
    }
    return LoginResponse(
        user=UserRead.model_validate(user),
        roles=roles,
        permissions=permissions,
        access_token=create_access_token(base_payload),
        refresh_token=create_refresh_token(base_payload),
    )


async def refresh_tokens(db: AsyncSession, refresh_token: str) -> TokenResponse:
    payload = decode_token(refresh_token)
    if payload.get("type") != "refresh":
        raise APIValidationException("Invalid refresh token")
    user_id = payload.get("sub")
    if not user_id:
        raise APIValidationException("Invalid refresh token payload")
    user = await db.get(User, int(user_id))
    if user is None or not user.is_active:
        raise APIValidationException("User not found or inactive")
    return await issue_tokens(db, user)
