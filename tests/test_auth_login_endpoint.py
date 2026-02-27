from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.domains.auth import router as auth_router
from app.domains.auth.schemas import LoginResponse


@pytest.mark.asyncio
async def test_login_accepts_json_payload(async_client, monkeypatch: pytest.MonkeyPatch) -> None:
    authenticate_mock = AsyncMock(return_value=SimpleNamespace(id=1))
    issue_login_response_mock = AsyncMock(
        return_value=LoginResponse(
            user={
                "id": 1,
                "email": "admin@bess.com",
                "full_name": "System Admin",
                "phone": None,
                "is_active": True,
                "is_verified": True,
            },
            roles=["SUPER_ADMIN"],
            permissions=["user:manage"],
            access_token="acc-json",
            refresh_token="ref-json",
        )
    )

    monkeypatch.setattr(auth_router.service, "authenticate", authenticate_mock)
    monkeypatch.setattr(auth_router.service, "issue_login_response", issue_login_response_mock)

    response = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "admin@bess.com", "password": "secret123"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["access_token"] == "acc-json"
    assert payload["refresh_token"] == "ref-json"
    assert payload["user"]["email"] == "admin@bess.com"
    assert payload["roles"] == ["SUPER_ADMIN"]
    assert payload["permissions"] == ["user:manage"]

    auth_payload = authenticate_mock.await_args.args[1]
    assert auth_payload.email == "admin@bess.com"
    assert auth_payload.password == "secret123"


@pytest.mark.asyncio
async def test_login_accepts_oauth_form_payload(async_client, monkeypatch: pytest.MonkeyPatch) -> None:
    authenticate_mock = AsyncMock(return_value=SimpleNamespace(id=2))
    issue_login_response_mock = AsyncMock(
        return_value=LoginResponse(
            user={
                "id": 2,
                "email": "admin@bess.com",
                "full_name": "System Admin",
                "phone": None,
                "is_active": True,
                "is_verified": True,
            },
            roles=["SUPER_ADMIN"],
            permissions=["user:manage"],
            access_token="acc-form",
            refresh_token="ref-form",
        )
    )

    monkeypatch.setattr(auth_router.service, "authenticate", authenticate_mock)
    monkeypatch.setattr(auth_router.service, "issue_login_response", issue_login_response_mock)

    response = await async_client.post(
        "/api/v1/auth/login",
        data={"username": "admin@bess.com", "password": "secret123"},
        headers={"content-type": "application/x-www-form-urlencoded"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["access_token"] == "acc-form"
    assert payload["refresh_token"] == "ref-form"
    assert payload["user"]["id"] == 2
    assert payload["roles"] == ["SUPER_ADMIN"]

    auth_payload = authenticate_mock.await_args.args[1]
    assert auth_payload.email == "admin@bess.com"
    assert auth_payload.password == "secret123"
