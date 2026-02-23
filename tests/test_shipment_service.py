from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.domains.shipment import service as shipment_service
from app.shared.exceptions import APIValidationException


@pytest.mark.asyncio
async def test_assign_unit_to_shipment_requires_order_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shipment = SimpleNamespace(id=1)
    unit = SimpleNamespace(id=1, is_deleted=False)
    monkeypatch.setattr(shipment_service.shipment_repository, "get_shipment", AsyncMock(return_value=shipment))
    monkeypatch.setattr(shipment_service.bess_repository, "get_by_id", AsyncMock(return_value=unit))

    with pytest.raises(APIValidationException):
        await shipment_service.assign_unit_to_shipment(
            db=object(),
            shipment_id=1,
            bess_unit_id=1,
            order_id="   ",
            current_user=SimpleNamespace(id=10),
        )
