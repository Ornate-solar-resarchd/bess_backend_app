from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Select, and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.engineer.models import Engineer, SiteAssignment
from app.domains.installation.models import ChecklistResponse, ChecklistTemplate
from app.shared.enums import AssignmentStatus, BESSStage


@dataclass(slots=True)
class ChecklistJoinedItem:
    checklist_template_id: int
    stage: BESSStage
    item_text: str
    description: str | None
    safety_warning: str | None
    is_mandatory: bool
    requires_photo: bool
    order_index: int
    is_checked: bool
    checked_by_user_id: int | None
    checked_at: object | None
    notes: str | None
    photo_url: str | None


class ChecklistRepository:
    async def get_templates_by_stage(self, db: AsyncSession, stage: BESSStage) -> list[ChecklistTemplate]:
        stmt: Select[tuple[ChecklistTemplate]] = (
            select(ChecklistTemplate)
            .where(ChecklistTemplate.stage == stage)
            .order_by(ChecklistTemplate.order_index.asc(), ChecklistTemplate.id.asc())
        )
        return list((await db.scalars(stmt)).all())

    async def get_response(
        self, db: AsyncSession, bess_unit_id: int, checklist_template_id: int
    ) -> ChecklistResponse | None:
        stmt = select(ChecklistResponse).where(
            ChecklistResponse.bess_unit_id == bess_unit_id,
            ChecklistResponse.checklist_template_id == checklist_template_id,
        )
        return await db.scalar(stmt)

    async def create_response(
        self,
        db: AsyncSession,
        bess_unit_id: int,
        template: ChecklistTemplate,
    ) -> ChecklistResponse:
        response = ChecklistResponse(
            bess_unit_id=bess_unit_id,
            checklist_template_id=template.id,
            stage=template.stage,
            is_checked=False,
        )
        db.add(response)
        await db.flush()
        return response

    async def get_stage_items(
        self,
        db: AsyncSession,
        bess_unit_id: int,
        stage: BESSStage,
    ) -> list[ChecklistJoinedItem]:
        stmt = (
            select(ChecklistTemplate, ChecklistResponse)
            .outerjoin(
                ChecklistResponse,
                and_(
                    ChecklistResponse.checklist_template_id == ChecklistTemplate.id,
                    ChecklistResponse.bess_unit_id == bess_unit_id,
                ),
            )
            .where(ChecklistTemplate.stage == stage)
            .order_by(ChecklistTemplate.order_index.asc(), ChecklistTemplate.id.asc())
        )
        rows = (await db.execute(stmt)).all()
        items: list[ChecklistJoinedItem] = []
        for template, response in rows:
            items.append(
                ChecklistJoinedItem(
                    checklist_template_id=template.id,
                    stage=template.stage,
                    item_text=template.item_text,
                    description=template.description,
                    safety_warning=template.safety_warning,
                    is_mandatory=template.is_mandatory,
                    requires_photo=template.requires_photo,
                    order_index=template.order_index,
                    is_checked=response.is_checked if response else False,
                    checked_by_user_id=response.checked_by_user_id if response else None,
                    checked_at=response.checked_at if response else None,
                    notes=response.notes if response else None,
                    photo_url=response.photo_url if response else None,
                )
            )
        return items

    async def get_incomplete_mandatory(
        self,
        db: AsyncSession,
        bess_unit_id: int,
        stage: BESSStage,
    ) -> list[str]:
        stage_items = await self.get_stage_items(db, bess_unit_id, stage)
        return [item.item_text for item in stage_items if item.is_mandatory and not item.is_checked]

    async def get_stage_checklist(
        self,
        db: AsyncSession,
        bess_unit_id: int,
        stage: BESSStage,
    ) -> list[ChecklistJoinedItem]:
        return await self.get_stage_items(db, bess_unit_id, stage)

    async def get_current_stage_engineer(
        self,
        db: AsyncSession,
        bess_unit_id: int,
        stage: BESSStage,
    ) -> Engineer | None:
        stmt = (
            select(Engineer)
            .join(SiteAssignment, SiteAssignment.engineer_id == Engineer.id)
            .where(
                SiteAssignment.bess_unit_id == bess_unit_id,
                SiteAssignment.assigned_stage == stage,
                SiteAssignment.status.in_(
                    [AssignmentStatus.PENDING, AssignmentStatus.ACCEPTED, AssignmentStatus.IN_PROGRESS]
                ),
            )
            .order_by(SiteAssignment.id.desc())
        )
        return await db.scalar(stmt)

    async def checklist_count_for_stage(self, db: AsyncSession, stage: BESSStage) -> int:
        stmt = select(func.count(ChecklistTemplate.id)).where(ChecklistTemplate.stage == stage)
        return int(await db.scalar(stmt) or 0)


checklist_repository = ChecklistRepository()
