from __future__ import annotations

import textwrap
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image, ImageDraw
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.domains.auth.models import User
from app.domains.bess_unit.models import AuditLog
from app.domains.bess_unit.repository import bess_repository
from app.domains.installation.models import ChecklistResponse, ChecklistTemplate
from app.domains.installation.repository import checklist_repository
from app.domains.installation.schemas import ChecklistValidationResponse
from app.shared.acid import atomic
from app.shared.enums import BESSStage
from app.shared.exceptions import APIConflictException, APIValidationException, APINotFoundException, BESSNotFoundException


async def get_stage_checklist(db: AsyncSession, bess_unit_id: int, stage: BESSStage):
    unit = await bess_repository.get_by_id(db, bess_unit_id)
    if unit is None or unit.is_deleted:
        raise BESSNotFoundException(bess_unit_id)
    return await checklist_repository.get_stage_items(db, bess_unit_id, stage)


async def update_checklist_item(
    db: AsyncSession,
    bess_unit_id: int,
    checklist_template_id: int,
    is_checked: bool,
    notes: str | None,
    photo_url: str | None,
    current_user: User,
) -> ChecklistResponse:
    unit = await bess_repository.get_by_id(db, bess_unit_id)
    if unit is None or unit.is_deleted:
        raise BESSNotFoundException(bess_unit_id)

    template = await db.get(ChecklistTemplate, checklist_template_id)
    if template is None:
        raise APINotFoundException("Checklist template item not found")

    normalized_photo = photo_url.strip() if photo_url else None
    if is_checked and not normalized_photo:
        raise APIValidationException(
            f"Photo is mandatory for checklist item '{template.item_text}' in stage '{template.stage.value}'"
        )

    async with atomic(db) as session:
        response = await checklist_repository.get_response(session, bess_unit_id, checklist_template_id)
        if response is None:
            response = await checklist_repository.create_response(session, bess_unit_id, template)

        response.is_checked = is_checked
        response.notes = notes
        response.photo_url = normalized_photo
        response.checked_by_user_id = current_user.id if is_checked else None
        response.checked_at = datetime.now(UTC) if is_checked else None
        await session.flush()

        await bess_repository.create_audit_log(
            session,
            AuditLog(
                user_id=current_user.id,
                action="CHECKLIST_UPDATE",
                entity_type="ChecklistResponse",
                entity_id=response.id,
                payload_json={
                    "bess_unit_id": bess_unit_id,
                    "checklist_template_id": checklist_template_id,
                    "is_checked": is_checked,
                },
            ),
        )

    return response


async def validate_stage_checklist(
    db: AsyncSession,
    bess_unit_id: int,
    stage: BESSStage,
) -> ChecklistValidationResponse:
    unit = await bess_repository.get_by_id(db, bess_unit_id)
    if unit is None or unit.is_deleted:
        raise BESSNotFoundException(bess_unit_id)

    pending = await checklist_repository.get_incomplete_mandatory(db, bess_unit_id, stage)
    return ChecklistValidationResponse(all_complete=not pending, pending_items=pending)


def _resolve_local_media_path(photo_url: str) -> Path | None:
    if not photo_url.startswith("/media/"):
        return None
    relative = photo_url[len("/media/") :]
    return Path(settings.media_root) / relative


def _draw_wrapped_text(draw: ImageDraw.ImageDraw, text: str, x: int, y: int, width_chars: int = 110) -> int:
    lines = textwrap.wrap(text, width=width_chars) or [text]
    for line in lines:
        draw.text((x, y), line, fill="black")
        y += 24
    return y


async def export_checklist_pdf(db: AsyncSession, bess_unit_id: int) -> Path:
    unit = await bess_repository.get_by_id(db, bess_unit_id)
    if unit is None or unit.is_deleted:
        raise BESSNotFoundException(bess_unit_id)

    pending_all: list[str] = []
    stage_items: list[tuple[BESSStage, list[object]]] = []
    for stage in BESSStage:
        items = await checklist_repository.get_stage_items(db, bess_unit_id, stage)
        if not items:
            continue
        stage_items.append((stage, items))
        for item in items:
            if item.is_mandatory and not item.is_checked:
                pending_all.append(f"{stage.value}: {item.item_text}")
    if pending_all:
        preview = "; ".join(pending_all[:3])
        suffix = "" if len(pending_all) <= 3 else f" (+{len(pending_all) - 3} more)"
        raise APIConflictException(
            f"Cannot generate final checklist PDF. Mandatory items are incomplete: {preview}{suffix}"
        )

    pages: list[Image.Image] = []
    page = Image.new("RGB", (1240, 1754), "white")
    draw = ImageDraw.Draw(page)
    y = 50

    y = _draw_wrapped_text(draw, f"BESS Checklist Report - {unit.serial_number}", 40, y)
    y = _draw_wrapped_text(draw, f"Generated at: {datetime.now(UTC).isoformat()}", 40, y)
    y += 10

    for stage, items in stage_items:
        if y > 1600:
            pages.append(page)
            page = Image.new("RGB", (1240, 1754), "white")
            draw = ImageDraw.Draw(page)
            y = 50
        y = _draw_wrapped_text(draw, f"Stage: {stage.value}", 40, y)
        y += 4
        for idx, item in enumerate(items, start=1):
            if y > 1550:
                pages.append(page)
                page = Image.new("RGB", (1240, 1754), "white")
                draw = ImageDraw.Draw(page)
                y = 50

            status = "DONE" if item.is_checked else "PENDING"
            y = _draw_wrapped_text(draw, f"{idx}. [{status}] {item.item_text}", 50, y)
            y = _draw_wrapped_text(draw, f"   Notes: {item.notes or '-'}", 50, y)
            y = _draw_wrapped_text(draw, f"   Photo: {item.photo_url or '-'}", 50, y)

            if item.photo_url:
                local_path = _resolve_local_media_path(item.photo_url)
                if local_path and local_path.exists():
                    try:
                        img = Image.open(local_path).convert("RGB")
                        img.thumbnail((280, 180))
                        page.paste(img, (860, y - 72))
                    except Exception:
                        pass
            y += 8

    pages.append(page)
    report_dir = Path(settings.media_root) / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    out_file = report_dir / f"checklist_report_bess_{bess_unit_id}_{int(datetime.now(UTC).timestamp())}.pdf"
    pages[0].save(out_file, "PDF", resolution=100.0, save_all=True, append_images=pages[1:])
    return out_file
