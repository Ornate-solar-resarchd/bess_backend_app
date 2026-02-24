from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import UploadFile

from app.domains.bess_unit import service as bess_service
from app.shared.enums import BESSStage
from app.shared.exceptions import (
    APIForbiddenException,
    APIValidationException,
    ChecklistIncompleteException,
    InvalidStageTransitionException,
)


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
    assert result.model_number == "UESS-215-418-EU-IN"
    assert result.can_register is True
    assert result.manufactured_date is not None
    assert result.manufactured_date.year == 2026
    assert result.manufactured_date.month == 1


@pytest.mark.asyncio
async def test_parse_qr_data_raises_on_empty_payload() -> None:
    with pytest.raises(APIValidationException):
        await bess_service.parse_qr_data("   ")


@pytest.mark.asyncio
async def test_transition_stage_requires_certificate_for_port_stage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    unit = SimpleNamespace(
        id=1,
        current_stage=BESSStage.PORT_ARRIVED,
        is_deleted=False,
        is_active=False,
        warehouse_id=1,
    )
    monkeypatch.setattr(bess_service.bess_repository, "get_by_id", AsyncMock(return_value=unit))
    monkeypatch.setattr(bess_service.bess_repository, "count_stage_certificates", AsyncMock(return_value=0))

    with pytest.raises(APIValidationException):
        await bess_service.transition_stage(
            bess_unit_id=1,
            to_stage=BESSStage.PORT_CLEARED,
            notes="try move without cert",
            current_user=SimpleNamespace(id=5),
            db=object(),
        )


@pytest.mark.asyncio
async def test_register_from_qr_rejects_warehouse_id_at_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = SimpleNamespace(
        qr_raw_data="Factory Code: TEST123456",
        serial_number_override=None,
        existing_qr_code_url=None,
        product_model_id=1,
        country_id=1,
        city_id=1,
        warehouse_id=1,
        site_address=None,
        site_latitude=None,
        site_longitude=None,
        customer_user_id=None,
        manufactured_date=None,
    )
    monkeypatch.setattr(bess_service, "_resolve_product_model_id", AsyncMock(return_value=1))

    with pytest.raises(APIValidationException):
        await bess_service.register_bess_from_qr(
            db=object(),
            payload=payload,
            current_user=SimpleNamespace(id=1),
        )


@pytest.mark.asyncio
async def test_list_bess_shipments_customer_scope_forbidden(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    unit = SimpleNamespace(id=1, is_deleted=False, customer_user_id=99)
    monkeypatch.setattr(bess_service.bess_repository, "get_by_id", AsyncMock(return_value=unit))

    with pytest.raises(APIForbiddenException):
        await bess_service.list_bess_shipments(
            db=object(),
            bess_unit_id=1,
            page=1,
            size=20,
            customer_user_id=10,
        )


@pytest.mark.asyncio
async def test_list_bess_shipments_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    unit = SimpleNamespace(id=1, is_deleted=False, customer_user_id=10)
    link = SimpleNamespace(
        shipment_id=2,
        order_id="PO-1001",
        created_at=datetime.now(UTC),
        shipment=SimpleNamespace(shipment_code="SHP-2", status="CREATED"),
    )
    monkeypatch.setattr(bess_service.bess_repository, "get_by_id", AsyncMock(return_value=unit))
    monkeypatch.setattr(
        bess_service.shipment_repository,
        "list_shipments_for_bess",
        AsyncMock(return_value=(1, [link])),
    )

    result = await bess_service.list_bess_shipments(
        db=object(),
        bess_unit_id=1,
        page=1,
        size=20,
        customer_user_id=10,
    )
    assert result.total == 1
    assert result.items[0].shipment_id == 2
    assert result.items[0].order_id == "PO-1001"


@pytest.mark.asyncio
async def test_register_from_photo_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    photo = UploadFile(filename="nameplate.jpg", file=BytesIO(b"dummy-image-bytes"))
    created = SimpleNamespace(id=7, serial_number="SN-001", nameplate_photo_url="/media/nameplates/a.jpg")

    monkeypatch.setattr(
        bess_service,
        "_save_uploaded_nameplate_photo",
        Mock(return_value="/media/nameplates/a.jpg"),
    )
    monkeypatch.setattr(
        bess_service,
        "_extract_text_from_nameplate_photo",
        Mock(return_value="Product Model: HESS-125-261-OS\nFactory Code: SN-001"),
    )
    monkeypatch.setattr(bess_service, "_resolve_product_model_id", AsyncMock(return_value=4))
    monkeypatch.setattr(bess_service, "create_bess_unit", AsyncMock(return_value=created))

    result = await bess_service.register_bess_from_photo(
        db=object(),
        photo=photo,
        country_id=1,
        city_id=1,
        current_user=SimpleNamespace(id=1),
    )

    assert result.id == 7
    assert result.nameplate_photo_url == "/media/nameplates/a.jpg"
    bess_service.create_bess_unit.assert_awaited_once()
    created_payload = bess_service.create_bess_unit.await_args.args[1]
    assert created_payload.serial_number == "SN-001"
    assert created_payload.nameplate_photo_url == "/media/nameplates/a.jpg"
    assert created_payload.product_model_id == 4


@pytest.mark.asyncio
async def test_register_from_photo_requires_serial(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    photo = UploadFile(filename="nameplate.jpg", file=BytesIO(b"dummy-image-bytes"))

    monkeypatch.setattr(
        bess_service,
        "_save_uploaded_nameplate_photo",
        Mock(return_value="/media/nameplates/a.jpg"),
    )
    monkeypatch.setattr(
        bess_service,
        "_extract_text_from_nameplate_photo",
        Mock(return_value="Product Model: UESS-125-261-OS\nMade Date: 2025.10"),
    )

    with pytest.raises(APIValidationException):
        await bess_service.register_bess_from_photo(
            db=object(),
            photo=photo,
            country_id=1,
            city_id=1,
            current_user=SimpleNamespace(id=1),
        )
