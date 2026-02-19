from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.domains.bess_unit.models import BESSUnit
from app.domains.engineer.repository import engineer_repository
from app.domains.engineer.service import auto_assign_engineer
from app.domains.installation.repository import checklist_repository
from app.shared.enums import BESSStage
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def auto_assign_engineer_task(self, bess_unit_id: int, stage: str):
    async def _runner() -> None:
        async with AsyncSessionLocal() as db:
            stage_enum = BESSStage(stage)
            existing = await engineer_repository.get_existing_assignment_for_stage(db, bess_unit_id, stage_enum)
            if existing is not None:
                return
            await auto_assign_engineer(bess_unit_id=bess_unit_id, stage=stage_enum, db=db)

    try:
        asyncio.run(_runner())
    except Exception as exc:  # noqa: BLE001
        logger.exception("Auto assignment failed for bess=%s stage=%s", bess_unit_id, stage)
        raise self.retry(exc=exc)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=30)
def notify_engineer_task(self, assignment_id: int):
    async def _runner() -> None:
        async with AsyncSessionLocal() as db:
            assignment = await engineer_repository.get_assignment(db, assignment_id)
            if assignment is None:
                return
            checklist_count = await checklist_repository.checklist_count_for_stage(db, assignment.assigned_stage)
            serial_stmt = select(BESSUnit.serial_number, BESSUnit.site_address).where(
                BESSUnit.id == assignment.bess_unit_id
            )
            serial_row = (await db.execute(serial_stmt)).first()
            serial_number = serial_row[0] if serial_row else "UNKNOWN"
            site_address = serial_row[1] if serial_row else None
            message = {
                "assignment_id": assignment_id,
                "serial_number": serial_number,
                "site_address": site_address,
                "assigned_stage": assignment.assigned_stage.value,
                "checklist_count": checklist_count,
                "scan_link": f"/api/v1/bess/scan/{serial_number}",
                "accept_link": f"/api/v1/assignments/{assignment_id}/accept",
                "decline_link": f"/api/v1/assignments/{assignment_id}/decline",
            }
            logger.info("Engineer notification payload: %s", message)

    try:
        asyncio.run(_runner())
    except Exception as exc:  # noqa: BLE001
        logger.exception("Engineer notification failed for assignment=%s", assignment_id)
        raise self.retry(exc=exc)
