from __future__ import annotations

import json
import textwrap
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.domains.auth.models import User
from app.domains.bess_unit.models import AuditLog
from app.domains.bess_unit.repository import bess_repository
from app.domains.installation.models import ChecklistResponse, ChecklistTemplate
from app.domains.installation.repository import checklist_repository
from app.domains.installation.schemas import ChecklistValidationResponse
from app.domains.installation.template_loader import DEFAULT_TEMPLATE_PATH
from app.shared.acid import atomic
from app.shared.enums import BESSStage
from app.shared.exceptions import APIConflictException, APIValidationException, APINotFoundException, BESSNotFoundException

_SIGNATURE_ENGINEER_MARKERS = ("qa team sign-off", "site engineer signature", "engineer signature")
_SIGNATURE_CUSTOMER_MARKERS = ("customer acceptance signature", "customer signature")
_PROJECT_ROOT = Path(__file__).resolve().parents[3]


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
    if is_checked and template.requires_photo and not normalized_photo:
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


def _load_template_meta() -> dict[str, str]:
    template_path = DEFAULT_TEMPLATE_PATH
    if not template_path.is_absolute():
        template_path = _PROJECT_ROOT / template_path

    try:
        raw: Any = json.loads(template_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(raw, dict):
        return {}

    meta = raw.get("_meta")
    if not isinstance(meta, dict):
        return {}

    normalized: dict[str, str] = {}
    for key, value in meta.items():
        if isinstance(value, str) and value.strip():
            normalized[key] = value.strip()
    return normalized


def _resolve_asset_path(raw_path: str | None) -> Path | None:
    if not raw_path:
        return None

    source = Path(raw_path)
    candidates = [source] if source.is_absolute() else [_PROJECT_ROOT / source, source]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _load_logo_image(
    meta: dict[str, str],
    keys: tuple[str, ...],
    max_width: int,
    max_height: int,
) -> Image.Image | None:
    for key in keys:
        logo_path = _resolve_asset_path(meta.get(key))
        if logo_path is None:
            continue
        try:
            logo = Image.open(logo_path).convert("RGBA")
            logo.thumbnail((max_width, max_height))
            return logo
        except Exception:
            continue
    return None


def _draw_report_logos(page: Image.Image) -> int:
    meta = _load_template_meta()
    brand_logo = _load_logo_image(meta, ("brand_logo",), 300, 110)
    checklist_logo = _load_logo_image(meta, ("checklist_logo_dark", "checklist_logo_light"), 420, 110)

    top_margin = 28
    left_margin = 40
    right_margin = 40
    max_logo_bottom = top_margin

    if brand_logo is not None:
        page.paste(brand_logo, (left_margin, top_margin), brand_logo)
        max_logo_bottom = max(max_logo_bottom, top_margin + int(brand_logo.height))
    if checklist_logo is not None:
        right_x = max(right_margin, int(page.width) - right_margin - int(checklist_logo.width))
        page.paste(checklist_logo, (right_x, top_margin), checklist_logo)
        max_logo_bottom = max(max_logo_bottom, top_margin + int(checklist_logo.height))

    return max(50, max_logo_bottom + 24)


def _public_media_url_for_path(file_path: Path) -> str:
    media_root = Path(settings.media_root).resolve()
    relative_path = file_path.resolve().relative_to(media_root).as_posix()
    return f"/media/{relative_path}"


def _draw_wrapped_text(draw: ImageDraw.ImageDraw, text: str, x: int, y: int, width_chars: int = 110) -> int:
    lines = textwrap.wrap(text, width=width_chars) or [text]
    for line in lines:
        draw.text((x, y), line, fill="black")
        y += 24
    return y


def _paste_photo_preview(
    page: Image.Image,
    photo_url: str,
    x: int,
    y: int,
    max_width: int = 280,
    max_height: int = 180,
) -> int:
    local_path = _resolve_local_media_path(photo_url)
    if local_path is None or not local_path.exists():
        return 0
    try:
        img = Image.open(local_path).convert("RGB")
        img.thumbnail((max_width, max_height))
        page.paste(img, (x, y))
        return int(img.height) + 8
    except Exception:
        return 0


def _contains_text_marker(item_text: str, markers: tuple[str, ...]) -> bool:
    normalized = item_text.strip().lower()
    return any(marker in normalized for marker in markers)


async def _resolve_user_name(db: AsyncSession, user_id: int | None, default_label: str) -> str:
    if user_id is None:
        return default_label
    user = await db.get(User, user_id)
    if user is None:
        return f"{default_label} (User #{user_id})"
    return user.full_name.strip() or f"{default_label} (User #{user_id})"


async def _collect_stage_items(db: AsyncSession, bess_unit_id: int) -> list[tuple[BESSStage, list[object]]]:
    stage_items: list[tuple[BESSStage, list[object]]] = []
    for stage in BESSStage:
        items = await checklist_repository.get_stage_items(db, bess_unit_id, stage)
        if not items:
            continue
        stage_items.append((stage, items))
    return stage_items


def _pending_mandatory_items(stage_items: list[tuple[BESSStage, list[object]]]) -> list[str]:
    pending_all: list[str] = []
    for stage, items in stage_items:
        for item in items:
            if item.is_mandatory and not item.is_checked:
                pending_all.append(f"{stage.value}: {item.item_text}")
    return pending_all


def _raise_if_pending_mandatory_items(stage_items: list[tuple[BESSStage, list[object]]], *, report_label: str) -> None:
    pending_all = _pending_mandatory_items(stage_items)
    if not pending_all:
        return
    preview = "; ".join(pending_all[:3])
    suffix = "" if len(pending_all) <= 3 else f" (+{len(pending_all) - 3} more)"
    raise APIConflictException(
        f"Cannot generate {report_label}. Mandatory items are incomplete: {preview}{suffix}"
    )


def _find_signature_items(stage_items: list[tuple[BESSStage, list[object]]]) -> tuple[object | None, object | None]:
    final_items = next((items for stage, items in stage_items if stage == BESSStage.FINAL_ACCEPTANCE), [])
    engineer_item = next(
        (item for item in final_items if _contains_text_marker(item.item_text, _SIGNATURE_ENGINEER_MARKERS)),
        None,
    )
    customer_item = next(
        (item for item in final_items if _contains_text_marker(item.item_text, _SIGNATURE_CUSTOMER_MARKERS)),
        None,
    )
    return engineer_item, customer_item


async def export_checklist_pdf(db: AsyncSession, bess_unit_id: int) -> Path:
    unit = await bess_repository.get_by_id(db, bess_unit_id)
    if unit is None or unit.is_deleted:
        raise BESSNotFoundException(bess_unit_id)

    stage_items = await _collect_stage_items(db, bess_unit_id)
    _raise_if_pending_mandatory_items(stage_items, report_label="final checklist PDF")

    pages: list[Image.Image] = []
    page = Image.new("RGB", (1240, 1754), "white")
    draw = ImageDraw.Draw(page)
    y = _draw_report_logos(page)

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
                y += _paste_photo_preview(page, item.photo_url, 860, max(y - 72, 50))
            y += 8

    pages.append(page)
    report_dir = Path(settings.media_root) / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    out_file = report_dir / f"checklist_report_bess_{bess_unit_id}_{int(datetime.now(UTC).timestamp())}.pdf"
    pages[0].save(out_file, "PDF", resolution=100.0, save_all=True, append_images=pages[1:])
    return out_file


async def export_handover_pdf(db: AsyncSession, bess_unit_id: int) -> Path:
    unit = await bess_repository.get_by_id(db, bess_unit_id)
    if unit is None or unit.is_deleted:
        raise BESSNotFoundException(bess_unit_id)

    stage_items = await _collect_stage_items(db, bess_unit_id)
    _raise_if_pending_mandatory_items(stage_items, report_label="handover document")

    engineer_signature_item, customer_signature_item = _find_signature_items(stage_items)
    engineer_signature_url = engineer_signature_item.photo_url if engineer_signature_item else None
    customer_signature_url = customer_signature_item.photo_url if customer_signature_item else None
    if not engineer_signature_url:
        raise APIConflictException(
            "Cannot generate handover document. Site engineer signature photo is missing in FINAL_ACCEPTANCE checklist."
        )
    if not customer_signature_url:
        raise APIConflictException(
            "Cannot generate handover document. Customer signature photo is missing in FINAL_ACCEPTANCE checklist."
        )

    engineer_name = await _resolve_user_name(
        db,
        engineer_signature_item.checked_by_user_id if engineer_signature_item else None,
        "Site Engineer",
    )
    customer_name = await _resolve_user_name(
        db,
        customer_signature_item.checked_by_user_id if customer_signature_item else unit.customer_user_id,
        "Customer",
    )

    model_number = "-"
    if getattr(unit, "product_model", None) is not None:
        model_number = getattr(unit.product_model, "model_number", "-")
    country_name = "-"
    if getattr(unit, "country", None) is not None:
        country_name = getattr(unit.country, "name", "-")
    city_name = "-"
    if getattr(unit, "city", None) is not None:
        city_name = getattr(unit.city, "name", "-")

    pages: list[Image.Image] = []
    page = Image.new("RGB", (1240, 1754), "white")
    draw = ImageDraw.Draw(page)
    y = _draw_report_logos(page)

    y = _draw_wrapped_text(draw, f"BESS Handover Document - {unit.serial_number}", 40, y)
    y = _draw_wrapped_text(draw, f"Generated at: {datetime.now(UTC).isoformat()}", 40, y)
    y = _draw_wrapped_text(draw, f"Model: {model_number}", 40, y)
    y = _draw_wrapped_text(draw, f"Location: {city_name}, {country_name}", 40, y)
    y = _draw_wrapped_text(draw, f"Site Address: {unit.site_address or '-'}", 40, y, width_chars=90)
    y += 8

    y = _draw_wrapped_text(draw, "Signatures", 40, y)
    y = _draw_wrapped_text(draw, f"Site Engineer: {engineer_name}", 50, y)
    y = _draw_wrapped_text(
        draw,
        f"Signed At: {engineer_signature_item.checked_at.isoformat() if engineer_signature_item and engineer_signature_item.checked_at else '-'}",
        50,
        y,
    )
    y = _draw_wrapped_text(draw, f"Signature Photo: {engineer_signature_url}", 50, y, width_chars=90)
    engineer_preview_height = _paste_photo_preview(page, engineer_signature_url, 760, max(y - 90, 50), 360, 180)
    if engineer_preview_height:
        y += engineer_preview_height
    y += 12

    y = _draw_wrapped_text(draw, f"Customer: {customer_name}", 50, y)
    y = _draw_wrapped_text(
        draw,
        f"Signed At: {customer_signature_item.checked_at.isoformat() if customer_signature_item and customer_signature_item.checked_at else '-'}",
        50,
        y,
    )
    y = _draw_wrapped_text(draw, f"Signature Photo: {customer_signature_url}", 50, y, width_chars=90)
    customer_preview_height = _paste_photo_preview(page, customer_signature_url, 760, max(y - 90, 50), 360, 180)
    if customer_preview_height:
        y += customer_preview_height
    y += 12

    for stage, items in stage_items:
        if y > 1560:
            pages.append(page)
            page = Image.new("RGB", (1240, 1754), "white")
            draw = ImageDraw.Draw(page)
            y = 50

        y = _draw_wrapped_text(draw, f"Stage: {stage.value}", 40, y)
        y += 4

        for idx, item in enumerate(items, start=1):
            if y > 1500:
                pages.append(page)
                page = Image.new("RGB", (1240, 1754), "white")
                draw = ImageDraw.Draw(page)
                y = 50

            status = "DONE" if item.is_checked else "PENDING"
            y = _draw_wrapped_text(draw, f"{idx}. [{status}] {item.item_text}", 50, y)
            y = _draw_wrapped_text(draw, f"   Notes: {item.notes or '-'}", 50, y)
            y = _draw_wrapped_text(draw, f"   Photo: {item.photo_url or '-'}", 50, y, width_chars=90)

            if item.photo_url:
                y += _paste_photo_preview(page, item.photo_url, 860, max(y - 72, 50))
            y += 8

    pages.append(page)

    report_dir = Path(settings.media_root) / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    out_file = report_dir / f"handover_document_bess_{bess_unit_id}.pdf"
    pages[0].save(out_file, "PDF", resolution=100.0, save_all=True, append_images=pages[1:])
    return out_file


async def ensure_handover_document(db: AsyncSession, bess_unit_id: int) -> str:
    out_file = await export_handover_pdf(db, bess_unit_id)
    return _public_media_url_for_path(out_file)
