from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.domains.auth import router as auth_router
from app.domains.auth.schemas import TokenResponse


@pytest.mark.asyncio
async def test_login_accepts_json_payload(async_client, monkeypatch: pytest.MonkeyPatch) -> None:
    authenticate_mock = AsyncMock(return_value=SimpleNamespace(id=1))
    issue_tokens_mock = AsyncMock(return_value=TokenResponse(access_token="acc-json", refresh_token="ref-json"))

    monkeypatch.setattr(auth_router.service, "authenticate", authenticate_mock)
    monkeypatch.setattr(auth_router.service, "issue_tokens", issue_tokens_mock)

    response = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "admin@bess.com", "password": "secret123"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["access_token"] == "acc-json"
    assert payload["refresh_token"] == "ref-json"

    auth_payload = authenticate_mock.await_args.args[1]
    assert auth_payload.email == "admin@bess.com"
    assert auth_payload.password == "secret123"


@pytest.mark.asyncio
async def test_login_accepts_oauth_form_payload(async_client, monkeypatch: pytest.MonkeyPatch) -> None:
    authenticate_mock = AsyncMock(return_value=SimpleNamespace(id=2))
    issue_tokens_mock = AsyncMock(return_value=TokenResponse(access_token="acc-form", refresh_token="ref-form"))

    monkeypatch.setattr(auth_router.service, "authenticate", authenticate_mock)
    monkeypatch.setattr(auth_router.service, "issue_tokens", issue_tokens_mock)

    response = await async_client.post(
        "/api/v1/auth/login",
        data={"username": "admin@bess.com", "password": "secret123"},
        headers={"content-type": "application/x-www-form-urlencoded"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["access_token"] == "acc-form"
    assert payload["refresh_token"] == "ref-form"

    auth_payload = authenticate_mock.await_args.args[1]
    assert auth_payload.email == "admin@bess.com"
    assert auth_payload.password == "secret123"
