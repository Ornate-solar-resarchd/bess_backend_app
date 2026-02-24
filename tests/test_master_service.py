from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.domains.master import service as master_service
from app.domains.master.schemas import ProductModelCreate
from app.shared.exceptions import APIConflictException


@asynccontextmanager
async def fake_atomic(_db: object):
    yield object()


@pytest.mark.asyncio
async def test_create_product_model_normalizes_hess_and_builds_description(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = SimpleNamespace(scalar=AsyncMock(return_value=None))
    captured: dict[str, object] = {}

    async def _fake_create(
        _session: object,
        model_number: str,
        capacity_kwh: float,
        description: str | None,
    ) -> SimpleNamespace:
        captured["model_number"] = model_number
        captured["capacity_kwh"] = capacity_kwh
        captured["description"] = description
        return SimpleNamespace(
            id=1,
            model_number=model_number,
            capacity_kwh=capacity_kwh,
            description=description,
        )

    monkeypatch.setattr(master_service, "atomic", fake_atomic)
    monkeypatch.setattr(master_service.master_repository, "create_product_model", _fake_create)
    monkeypatch.setattr(master_service.bess_repository, "create_audit_log", AsyncMock(return_value=None))

    payload = ProductModelCreate(
        model_number="HESS-125-261-OS",
        capacity_kwh=261.0,
        description="HESS base description",
        spec_fields={
            "product_model": "HESS-125-261-OS",
            "system_rated_energy": "261kWh",
            "iec_designation": "IfpP73/176/208",
        },
    )

    result = await master_service.create_product_model(
        db=db,
        payload=payload,
        current_user=SimpleNamespace(id=100),
    )

    assert result.model_number == "UESS-125-261-OS"
    assert "UESS base description" in str(captured["description"])
    assert "Product Model: UESS-125-261-OS" in str(captured["description"])
    assert "Iec Designation" not in str(captured["description"])


@pytest.mark.asyncio
async def test_create_product_model_rejects_duplicate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = SimpleNamespace(scalar=AsyncMock(return_value=SimpleNamespace(id=1)))
    payload = ProductModelCreate(
        model_number="HESS-125-261-OS",
        capacity_kwh=261.0,
    )

    with pytest.raises(APIConflictException):
        await master_service.create_product_model(
            db=db,
            payload=payload,
            current_user=SimpleNamespace(id=100),
        )
