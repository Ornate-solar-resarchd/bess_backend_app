from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.core.dependencies import AuthContext, require_permission, require_role


@pytest.mark.asyncio
async def test_require_permission_allows_user_with_permission() -> None:
    checker = require_permission("bess:read")
    context = AuthContext(
        user=SimpleNamespace(id=1),
        roles=["SITE_ENGINEER"],
        permissions=["bess:read", "checklist:write"],
    )

    user = await checker(context=context)
    assert user.id == 1


@pytest.mark.asyncio
async def test_require_permission_rejects_user_without_permission() -> None:
    checker = require_permission("bess:transition")
    context = AuthContext(
        user=SimpleNamespace(id=1),
        roles=["SITE_ENGINEER"],
        permissions=["bess:read"],
    )

    with pytest.raises(HTTPException) as exc_info:
        await checker(context=context)

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_require_role_allows_any_matching_role() -> None:
    checker = require_role("SUPER_ADMIN", "FACTORY_ADMIN")
    context = AuthContext(
        user=SimpleNamespace(id=2),
        roles=["FACTORY_ADMIN"],
        permissions=[],
    )

    user = await checker(context=context)
    assert user.id == 2


@pytest.mark.asyncio
async def test_require_role_rejects_when_no_roles_match() -> None:
    checker = require_role("SUPER_ADMIN")
    context = AuthContext(
        user=SimpleNamespace(id=3),
        roles=["CUSTOMER"],
        permissions=[],
    )

    with pytest.raises(HTTPException) as exc_info:
        await checker(context=context)

    assert exc_info.value.status_code == 403
