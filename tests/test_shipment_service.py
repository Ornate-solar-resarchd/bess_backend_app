from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.domains.shipment import service as shipment_service
from app.shared.enums import ShipmentStatus
from app.shared.exceptions import APIConflictException, APIValidationException


@asynccontextmanager
async def fake_atomic(_db: object):
    class _DummySession:
        async def flush(self) -> None:
            return None

        async def execute(self, _stmt: object):
            class _Result:
                def scalars(self):
                    class _Scalars:
                        def all(self):
                            return []

                    return _Scalars()

            return _Result()

    yield _DummySession()


@pytest.mark.asyncio
async def test_assign_unit_to_shipment_requires_order_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shipment = SimpleNamespace(id=1)
    unit = SimpleNamespace(id=1, is_deleted=False)
    monkeypatch.setattr(shipment_service.shipment_repository, "get_shipment", AsyncMock(return_value=shipment))
    monkeypatch.setattr(shipment_service.bess_repository, "get_by_id", AsyncMock(return_value=unit))
    monkeypatch.setattr(shipment_service.shipment_repository, "item_exists", AsyncMock(return_value=False))
    monkeypatch.setattr(shipment_service.shipment_repository, "find_shipment_for_bess", AsyncMock(return_value=None))

    with pytest.raises(APIValidationException):
        await shipment_service.assign_unit_to_shipment(
            db=object(),
            shipment_id=1,
            bess_unit_id=1,
            order_id="   ",
            current_user=SimpleNamespace(id=10),
        )


@pytest.mark.asyncio
async def test_assign_unit_to_shipment_rejects_duplicate_item(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shipment = SimpleNamespace(id=1)
    unit = SimpleNamespace(id=1, is_deleted=False)
    monkeypatch.setattr(shipment_service.shipment_repository, "get_shipment", AsyncMock(return_value=shipment))
    monkeypatch.setattr(shipment_service.bess_repository, "get_by_id", AsyncMock(return_value=unit))
    monkeypatch.setattr(shipment_service.shipment_repository, "item_exists", AsyncMock(return_value=True))
    monkeypatch.setattr(shipment_service.shipment_repository, "find_shipment_for_bess", AsyncMock(return_value=1))

    with pytest.raises(APIConflictException):
        await shipment_service.assign_unit_to_shipment(
            db=object(),
            shipment_id=1,
            bess_unit_id=1,
            order_id="PO-1",
            current_user=SimpleNamespace(id=10),
        )


@pytest.mark.asyncio
async def test_assign_unit_to_shipment_rejects_existing_other_shipment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shipment = SimpleNamespace(id=2)
    unit = SimpleNamespace(id=1, is_deleted=False)
    monkeypatch.setattr(shipment_service.shipment_repository, "get_shipment", AsyncMock(return_value=shipment))
    monkeypatch.setattr(shipment_service.bess_repository, "get_by_id", AsyncMock(return_value=unit))
    monkeypatch.setattr(shipment_service.shipment_repository, "item_exists", AsyncMock(return_value=False))
    monkeypatch.setattr(shipment_service.shipment_repository, "find_shipment_for_bess", AsyncMock(return_value=5))

    with pytest.raises(APIConflictException):
        await shipment_service.assign_unit_to_shipment(
            db=object(),
            shipment_id=2,
            bess_unit_id=1,
            order_id="PO-1",
            current_user=SimpleNamespace(id=10),
        )


@pytest.mark.asyncio
async def test_update_shipment_status_packed_requires_quantity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shipment = SimpleNamespace(id=1, expected_quantity=3, status=ShipmentStatus.CREATED)
    monkeypatch.setattr(shipment_service.shipment_repository, "get_shipment", AsyncMock(return_value=shipment))
    monkeypatch.setattr(shipment_service.shipment_repository, "count_shipment_items", AsyncMock(return_value=2))

    with pytest.raises(APIConflictException):
        await shipment_service.update_shipment_status(
            db=object(),
            shipment_id=1,
            status=ShipmentStatus.PACKED,
            current_user=SimpleNamespace(id=10),
        )


@pytest.mark.asyncio
async def test_update_shipment_status_packed_requires_documents(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shipment = SimpleNamespace(id=1, expected_quantity=2, status=ShipmentStatus.CREATED)
    monkeypatch.setattr(shipment_service.shipment_repository, "get_shipment", AsyncMock(return_value=shipment))
    monkeypatch.setattr(shipment_service.shipment_repository, "count_shipment_items", AsyncMock(return_value=2))
    monkeypatch.setattr(shipment_service.shipment_repository, "count_documents", AsyncMock(return_value=0))

    with pytest.raises(APIConflictException):
        await shipment_service.update_shipment_status(
            db=object(),
            shipment_id=1,
            status=ShipmentStatus.PACKED,
            current_user=SimpleNamespace(id=10),
        )


@pytest.mark.asyncio
async def test_update_shipment_status_packed_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shipment = SimpleNamespace(id=1, expected_quantity=2, status=ShipmentStatus.CREATED)
    monkeypatch.setattr(shipment_service, "atomic", fake_atomic)
    monkeypatch.setattr(shipment_service.shipment_repository, "get_shipment", AsyncMock(return_value=shipment))
    monkeypatch.setattr(shipment_service.shipment_repository, "count_shipment_items", AsyncMock(return_value=2))
    monkeypatch.setattr(shipment_service.shipment_repository, "count_documents", AsyncMock(return_value=1))
    monkeypatch.setattr(shipment_service.bess_repository, "create_audit_log", AsyncMock(return_value=None))

    result = await shipment_service.update_shipment_status(
        db=object(),
        shipment_id=1,
        status=ShipmentStatus.PACKED,
        current_user=SimpleNamespace(id=10),
    )
    assert result.status == ShipmentStatus.PACKED


@pytest.mark.asyncio
async def test_get_shipment_detail_returns_units_and_documents(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shipment = SimpleNamespace(
        id=1,
        shipment_code="SHP-1",
        origin_country_id=1,
        destination_country_id=2,
        expected_quantity=2,
        status=ShipmentStatus.CREATED,
    )
    unit_item = SimpleNamespace(id=11, shipment_id=1, bess_unit_id=100, order_id="PO-1")
    doc_item = SimpleNamespace(
        id=21,
        shipment_id=1,
        document_name="BOL",
        document_type="BOL",
        document_url="/media/shipment_documents/1/bol.pdf",
        notes=None,
        uploaded_by_user_id=10,
        uploaded_at="2026-01-01T00:00:00Z",
    )
    monkeypatch.setattr(shipment_service.shipment_repository, "get_shipment", AsyncMock(return_value=shipment))
    monkeypatch.setattr(shipment_service.shipment_repository, "list_all_shipment_items", AsyncMock(return_value=[unit_item]))
    monkeypatch.setattr(shipment_service.shipment_repository, "list_all_documents", AsyncMock(return_value=[doc_item]))

    result = await shipment_service.get_shipment_detail(db=object(), shipment_id=1)
    assert result.shipment.id == 1
    assert result.units_total == 1
    assert result.documents_total == 1


@pytest.mark.asyncio
async def test_bulk_assign_rejects_existing_other_shipment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shipment = SimpleNamespace(id=7)
    unit = SimpleNamespace(id=101, is_deleted=False)
    payload = SimpleNamespace(items=[SimpleNamespace(bess_unit_id=101, order_id="PO-7")])
    monkeypatch.setattr(shipment_service.shipment_repository, "get_shipment", AsyncMock(return_value=shipment))
    monkeypatch.setattr(shipment_service.bess_repository, "get_by_id", AsyncMock(return_value=unit))
    monkeypatch.setattr(shipment_service.shipment_repository, "item_exists", AsyncMock(return_value=False))
    monkeypatch.setattr(shipment_service.shipment_repository, "find_shipment_for_bess", AsyncMock(return_value=3))

    with pytest.raises(APIConflictException):
        await shipment_service.assign_units_to_shipment_bulk(
            db=object(),
            shipment_id=7,
            payload=payload,
            current_user=SimpleNamespace(id=99),
        )
