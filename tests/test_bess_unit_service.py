from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.domains.bess_unit import service as bess_service
from app.shared.enums import BESSStage
from app.shared.exceptions import APIValidationException, ChecklistIncompleteException, InvalidStageTransitionException


@asynccontextmanager
async def fake_atomic(_db: object, serializable: bool = False):
    class _DummySession:
        async def flush(self) -> None:
            return None

    _ = serializable
    yield _DummySession()


@pytest.mark.asyncio
async def test_transition_stage_rejects_invalid_transition(monkeypatch: pytest.MonkeyPatch) -> None:
    unit = SimpleNamespace(
        id=1,
        current_stage=BESSStage.FACTORY_REGISTERED,
        is_deleted=False,
        is_active=False,
    )

    monkeypatch.setattr(bess_service.bess_repository, "get_by_id", AsyncMock(return_value=unit))

    with pytest.raises(InvalidStageTransitionException):
        await bess_service.transition_stage(
            bess_unit_id=1,
            to_stage=BESSStage.PACKED,
            notes=None,
            current_user=SimpleNamespace(id=99),
            db=object(),
        )


@pytest.mark.asyncio
async def test_transition_stage_rejects_when_checklist_incomplete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    unit = SimpleNamespace(
        id=1,
        current_stage=BESSStage.FACTORY_REGISTERED,
        is_deleted=False,
        is_active=False,
    )

    monkeypatch.setattr(bess_service.bess_repository, "get_by_id", AsyncMock(return_value=unit))
    monkeypatch.setattr(
        bess_service.checklist_repository,
        "get_incomplete_mandatory",
        AsyncMock(return_value=["Verify serial number matches delivery note"]),
    )

    with pytest.raises(ChecklistIncompleteException):
        await bess_service.transition_stage(
            bess_unit_id=1,
            to_stage=BESSStage.SHIPMENT_ASSIGNED,
            notes="Attempt transition",
            current_user=SimpleNamespace(id=99),
            db=object(),
        )


@pytest.mark.asyncio
async def test_transition_stage_success_updates_state_and_triggers_auto_assign(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    unit = SimpleNamespace(
        id=1,
        current_stage=BESSStage.DISPATCHED_TO_SITE,
        is_deleted=False,
        is_active=False,
    )

    create_history = AsyncMock()
    create_audit = AsyncMock()
    delay_mock = Mock()

    monkeypatch.setattr(bess_service, "atomic", fake_atomic)
    monkeypatch.setattr(bess_service.bess_repository, "get_by_id", AsyncMock(return_value=unit))
    monkeypatch.setattr(
        bess_service.checklist_repository,
        "get_incomplete_mandatory",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(bess_service.bess_repository, "create_stage_history", create_history)
    monkeypatch.setattr(bess_service.bess_repository, "create_audit_log", create_audit)
    monkeypatch.setattr(bess_service.auto_assign_engineer_task, "delay", delay_mock)

    result = await bess_service.transition_stage(
        bess_unit_id=1,
        to_stage=BESSStage.SITE_ARRIVED,
        notes="Moved to site",
        current_user=SimpleNamespace(id=10),
        db=object(),
    )

    assert result.current_stage == BESSStage.SITE_ARRIVED
    assert result.is_active is False
    assert create_history.await_count == 1
    assert create_audit.await_count == 1
    delay_mock.assert_called_once_with(1, BESSStage.SITE_ARRIVED.value)


def test_ensure_qr_file_creates_png(tmp_path: object, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bess_service.settings, "media_root", str(tmp_path))
    monkeypatch.setattr(bess_service.settings, "qr_code_base_url", "https://example.com")

    qr_url, file_path = bess_service._ensure_qr_file("SERIAL123")

    assert qr_url == "/media/qr/SERIAL123.png"
    assert file_path.exists()
    assert file_path.suffix == ".png"
    assert datetime.now(UTC)


@pytest.mark.asyncio
async def test_parse_qr_data_extracts_factory_fields() -> None:
    raw = (
        "Product Model: HESS-215-418-EU-IN\n"
        "Made Date: 2026.1\n"
        "Factory Code: EESB2LFPL8001331215418260001"
    )
    result = await bess_service.parse_qr_data(raw)
    assert result.serial_number == "EESB2LFPL8001331215418260001"
    assert result.model_number == "HESS-215-418-EU-IN"
    assert result.can_register is True
    assert result.manufactured_date is not None
    assert result.manufactured_date.year == 2026
    assert result.manufactured_date.month == 1


@pytest.mark.asyncio
async def test_parse_qr_data_raises_on_empty_payload() -> None:
    with pytest.raises(APIValidationException):
        await bess_service.parse_qr_data("   ")
