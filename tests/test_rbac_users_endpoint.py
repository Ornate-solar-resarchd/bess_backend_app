from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.database import get_db
from app.core.dependencies import AuthContext, get_auth_context
from app.domains.rbac import router as rbac_router
from app.main import app


@pytest.mark.asyncio
async def test_admin_users_requires_auth(async_client) -> None:
    response = await async_client.get("/api/v1/admin/users")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_users_requires_user_manage_permission(async_client) -> None:
    async def _override_auth_context() -> AuthContext:
        return AuthContext(
            user=SimpleNamespace(id=10),
            roles=["FACTORY_ADMIN"],
            permissions=["bess:read"],
        )

    app.dependency_overrides[get_auth_context] = _override_auth_context
    try:
        response = await async_client.get("/api/v1/admin/users")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_users_returns_paginated_payload(async_client, monkeypatch: pytest.MonkeyPatch) -> None:
    db_marker = object()
    list_users_mock = AsyncMock(
        return_value=(
            2,
            [
                SimpleNamespace(
                    id=1,
                    email="john@example.com",
                    full_name="John Doe",
                    phone="9999999999",
                    is_active=True,
                    is_verified=True,
                ),
                SimpleNamespace(
                    id=2,
                    email="jane@example.com",
                    full_name="Jane Doe",
                    phone=None,
                    is_active=False,
                    is_verified=False,
                ),
            ],
        )
    )

    monkeypatch.setattr(rbac_router, "list_users", list_users_mock)

    async def _override_db():
        yield db_marker

    async def _override_auth_context() -> AuthContext:
        return AuthContext(
            user=SimpleNamespace(id=1),
            roles=["SUPER_ADMIN"],
            permissions=["user:manage"],
        )

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_auth_context] = _override_auth_context
    try:
        response = await async_client.get(
            "/api/v1/admin/users",
            params={"page": 2, "size": 10, "q": "doe", "is_active": "false"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2
    assert payload["page"] == 2
    assert payload["size"] == 10
    assert len(payload["items"]) == 2
    assert payload["items"][0]["email"] == "john@example.com"
    assert payload["items"][1]["is_active"] is False

    args = list_users_mock.await_args.args
    assert args[0] is db_marker
    assert args[1:] == (2, 10, "doe", False)
