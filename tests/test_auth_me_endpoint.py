from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.dependencies import AuthContext, get_auth_context
from app.main import app


@pytest.mark.asyncio
async def test_me_requires_auth(async_client) -> None:
    response = await async_client.get("/api/v1/auth/me")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_me_returns_user_roles_permissions(async_client) -> None:
    async def _override_auth_context() -> AuthContext:
        return AuthContext(
            user=SimpleNamespace(
                id=11,
                email="dharmendra@ornatesolar.com",
                full_name="Dharmendra",
                phone="9000000010",
                is_active=True,
                is_verified=False,
            ),
            roles=["CUSTOMER"],
            permissions=["bess:read", "report:view"],
        )

    app.dependency_overrides[get_auth_context] = _override_auth_context
    try:
        response = await async_client.get("/api/v1/auth/me")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["user"]["email"] == "dharmendra@ornatesolar.com"
    assert payload["roles"] == ["CUSTOMER"]
    assert payload["permissions"] == ["bess:read", "report:view"]
