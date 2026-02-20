from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.domains.bess_unit.router import service as bess_router_service
from app.domains.bess_unit.schemas import BESSUnitRead, NestedNamed, NestedProductModel, ScanResponse
from app.shared.enums import BESSStage


@pytest.mark.asyncio
async def test_public_scan_endpoint_returns_payload(
    async_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(UTC)
    sample = ScanResponse(
        bess_unit=BESSUnitRead(
            id=1,
            serial_number="BESS-TEST-001",
            qr_code_url="/media/qr/BESS-TEST-001.png",
            current_stage=BESSStage.FACTORY_REGISTERED,
            is_active=False,
            product_model=NestedProductModel(id=1, model_number="UNITYESS-125-261-OS", capacity_kwh=261.0),
            country=NestedNamed(id=1, name="India"),
            city=NestedNamed(id=1, name="Delhi"),
            warehouse=None,
            site_address=None,
            site_latitude=None,
            site_longitude=None,
            customer_user_id=None,
            manufactured_date=None,
            created_at=now,
            updated_at=now,
        ),
        product_specs=NestedProductModel(id=1, model_number="UNITYESS-125-261-OS", capacity_kwh=261.0),
        current_stage=BESSStage.FACTORY_REGISTERED,
        assigned_engineer=None,
        checklist=[],
        stage_instructions="Factory registered",
    )

    async def _fake_scan(_db, _serial: str) -> ScanResponse:
        return sample

    monkeypatch.setattr(bess_router_service, "scan_by_serial", _fake_scan)

    response = await async_client.get("/api/v1/bess/scan/BESS-TEST-001")

    assert response.status_code == 200
    payload = response.json()
    assert payload["bess_unit"]["serial_number"] == "BESS-TEST-001"
    assert payload["current_stage"] == "FACTORY_REGISTERED"


@pytest.mark.asyncio
async def test_protected_bess_list_requires_auth(async_client) -> None:
    response = await async_client.get("/api/v1/bess/")
    assert response.status_code == 401
