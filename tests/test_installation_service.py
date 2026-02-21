from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.domains.installation import service as installation_service
from app.shared.enums import BESSStage
from app.shared.exceptions import APIValidationException


@asynccontextmanager
async def fake_atomic(_db: object, serializable: bool = False):
    _ = serializable
    class _DummySession:
        async def flush(self) -> None:
            return None

    yield _DummySession()


@pytest.mark.asyncio
async def test_update_checklist_requires_photo_for_installation_stage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    unit = SimpleNamespace(id=1, is_deleted=False)
    template = SimpleNamespace(
        id=11,
        item_text="Civil check",
        stage=BESSStage.CIVIL_INSTALLATION,
        requires_photo=False,
    )
    db = SimpleNamespace(get=AsyncMock(return_value=template))

    monkeypatch.setattr(installation_service.bess_repository, "get_by_id", AsyncMock(return_value=unit))

    with pytest.raises(APIValidationException):
        await installation_service.update_checklist_item(
            db=db,
            bess_unit_id=1,
            checklist_template_id=11,
            is_checked=True,
            notes="done",
            photo_url=None,
            current_user=SimpleNamespace(id=9),
        )


@pytest.mark.asyncio
async def test_update_checklist_allows_installation_stage_when_photo_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    unit = SimpleNamespace(id=1, is_deleted=False)
    template = SimpleNamespace(
        id=11,
        item_text="Civil check",
        stage=BESSStage.CIVIL_INSTALLATION,
        requires_photo=False,
    )
    response = SimpleNamespace(
        id=100,
        is_checked=False,
        notes=None,
        photo_url=None,
        checked_by_user_id=None,
        checked_at=None,
    )
    db = SimpleNamespace(get=AsyncMock(return_value=template))

    monkeypatch.setattr(installation_service, "atomic", fake_atomic)
    monkeypatch.setattr(installation_service.bess_repository, "get_by_id", AsyncMock(return_value=unit))
    monkeypatch.setattr(installation_service.checklist_repository, "get_response", AsyncMock(return_value=response))
    monkeypatch.setattr(installation_service.checklist_repository, "create_response", AsyncMock(return_value=response))
    monkeypatch.setattr(installation_service.bess_repository, "create_audit_log", AsyncMock(return_value=None))

    updated = await installation_service.update_checklist_item(
        db=db,
        bess_unit_id=1,
        checklist_template_id=11,
        is_checked=True,
        notes="done",
        photo_url=" https://example.com/photo.jpg ",
        current_user=SimpleNamespace(id=9),
    )

    assert updated.is_checked is True
    assert updated.photo_url == "https://example.com/photo.jpg"
    assert updated.checked_by_user_id == 9
