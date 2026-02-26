from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.domains.installation import service as installation_service
from app.shared.enums import BESSStage
from app.shared.exceptions import APIConflictException, APIValidationException


@asynccontextmanager
async def fake_atomic(_db: object, serializable: bool = False):
    _ = serializable
    class _DummySession:
        async def flush(self) -> None:
            return None

    yield _DummySession()


@pytest.mark.asyncio
async def test_update_checklist_does_not_require_photo_when_template_flag_is_false(
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
        photo_url=None,
        current_user=SimpleNamespace(id=9),
    )

    assert updated.is_checked is True
    assert updated.photo_url is None


@pytest.mark.asyncio
async def test_update_checklist_requires_photo_when_template_flag_is_true(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    unit = SimpleNamespace(id=1, is_deleted=False)
    template = SimpleNamespace(
        id=11,
        item_text="Civil check",
        stage=BESSStage.CIVIL_INSTALLATION,
        requires_photo=True,
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


@pytest.mark.asyncio
async def test_export_handover_pdf_requires_customer_signature(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(UTC)
    unit = SimpleNamespace(
        id=1,
        serial_number="BESS-001",
        is_deleted=False,
        site_address="Test site",
        customer_user_id=55,
        product_model=SimpleNamespace(model_number="UESS-125-261-OS"),
        country=SimpleNamespace(name="India"),
        city=SimpleNamespace(name="Delhi"),
    )

    engineer_item = SimpleNamespace(
        is_mandatory=True,
        is_checked=True,
        item_text="QA team sign-off obtained",
        notes="signed",
        photo_url="/media/checklist_photos/engineer-sign.png",
        checked_by_user_id=9,
        checked_at=now,
    )
    customer_item = SimpleNamespace(
        is_mandatory=True,
        is_checked=True,
        item_text="Customer acceptance signature collected",
        notes="pending upload",
        photo_url=None,
        checked_by_user_id=55,
        checked_at=now,
    )

    class _FakeDB:
        async def get(self, _model: object, user_id: int):
            if user_id == 9:
                return SimpleNamespace(full_name="Engineer One")
            if user_id == 55:
                return SimpleNamespace(full_name="Customer One")
            return None

    async def _fake_stage_items(_db: object, _bess_id: int, stage: BESSStage):
        if stage == BESSStage.FINAL_ACCEPTANCE:
            return [engineer_item, customer_item]
        return []

    monkeypatch.setattr(installation_service.settings, "media_root", str(tmp_path))
    monkeypatch.setattr(
        installation_service.bess_repository,
        "get_by_id",
        AsyncMock(return_value=unit),
    )
    monkeypatch.setattr(
        installation_service.checklist_repository,
        "get_stage_items",
        _fake_stage_items,
    )

    with pytest.raises(APIConflictException):
        await installation_service.export_handover_pdf(_FakeDB(), 1)


@pytest.mark.asyncio
async def test_export_handover_pdf_creates_document_when_signatures_present(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(UTC)
    unit = SimpleNamespace(
        id=1,
        serial_number="BESS-001",
        is_deleted=False,
        site_address="Test site",
        customer_user_id=55,
        product_model=SimpleNamespace(model_number="UESS-125-261-OS"),
        country=SimpleNamespace(name="India"),
        city=SimpleNamespace(name="Delhi"),
    )

    engineer_item = SimpleNamespace(
        is_mandatory=True,
        is_checked=True,
        item_text="QA team sign-off obtained",
        notes="signed",
        photo_url="/media/checklist_photos/engineer-sign.png",
        checked_by_user_id=9,
        checked_at=now,
    )
    customer_item = SimpleNamespace(
        is_mandatory=True,
        is_checked=True,
        item_text="Customer acceptance signature collected",
        notes="signed",
        photo_url="/media/checklist_photos/customer-sign.png",
        checked_by_user_id=55,
        checked_at=now,
    )
    civil_item = SimpleNamespace(
        is_mandatory=True,
        is_checked=True,
        item_text="Foundation complete",
        notes="done",
        photo_url=None,
        checked_by_user_id=9,
        checked_at=now,
    )

    class _FakeDB:
        async def get(self, _model: object, user_id: int):
            if user_id == 9:
                return SimpleNamespace(full_name="Engineer One")
            if user_id == 55:
                return SimpleNamespace(full_name="Customer One")
            return None

    async def _fake_stage_items(_db: object, _bess_id: int, stage: BESSStage):
        if stage == BESSStage.FINAL_ACCEPTANCE:
            return [engineer_item, customer_item]
        if stage == BESSStage.CIVIL_INSTALLATION:
            return [civil_item]
        return []

    monkeypatch.setattr(installation_service.settings, "media_root", str(tmp_path))
    monkeypatch.setattr(
        installation_service.bess_repository,
        "get_by_id",
        AsyncMock(return_value=unit),
    )
    monkeypatch.setattr(
        installation_service.checklist_repository,
        "get_stage_items",
        _fake_stage_items,
    )

    output = await installation_service.export_handover_pdf(_FakeDB(), 1)

    assert output.exists()
    assert output.name == "handover_document_bess_1.pdf"
