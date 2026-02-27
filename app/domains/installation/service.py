from __future__ import annotations

import json
import textwrap
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw
from qrcode import QRCode
from qrcode.constants import ERROR_CORRECT_M
from qrcode.exceptions import DataOverflowError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.domains.auth.models import User
from app.domains.bess_unit.models import AuditLog
from app.domains.bess_unit.repository import bess_repository
from app.domains.installation.models import ChecklistResponse, ChecklistTemplate
from app.domains.installation.repository import checklist_repository
from app.domains.installation.schemas import (
    ChecklistValidationResponse,
    HandoverBESSDetailsRead,
    HandoverBrandingRead,
    HandoverChecklistItemRead,
    HandoverChecklistStageRead,
    HandoverDocumentDataRead,
    HandoverSignatureRead,
)
from app.domains.installation.template_loader import DEFAULT_TEMPLATE_PATH
from app.shared.acid import atomic
from app.shared.enums import BESSStage
from app.shared.exceptions import APIConflictException, APIValidationException, APINotFoundException, BESSNotFoundException

_SIGNATURE_ENGINEER_MARKERS = ("qa team sign-off", "site engineer signature", "engineer signature")
_SIGNATURE_CUSTOMER_MARKERS = ("customer acceptance signature", "customer signature")
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_PAGE_WIDTH = 1240
_PAGE_HEIGHT = 1754
_REPORT_BG = (255, 247, 241)
_REPORT_HEADER_BG = (17, 20, 24)
_REPORT_ACCENT = (255, 102, 77)
_REPORT_TEXT = (22, 22, 24)
_REPORT_SECTION_BG = (255, 232, 220)
_HANDOVER_REFERENCES = [
    "CEA Grid Connectivity Regulations: https://cea.nic.in/regulations-category/connectivity-to-the-grid/",
    "MNRE ESS Policies: https://mnre.gov.in/en/energy-storage-systemsess-policies-and-guidelines/",
    "National ESS Framework: https://powermin.gov.in/sites/default/files/National_Framework_for_promoting_Energy_Storage_Systems_August_2023.pdf",
]


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
    draw = ImageDraw.Draw(page, "RGBA")
    draw.rectangle((0, 0, page.width, page.height), fill=(*_REPORT_BG, 255))
    draw.rectangle((0, 0, page.width, 150), fill=(*_REPORT_HEADER_BG, 255))
    draw.polygon(
        [
            (page.width - 290, 0),
            (page.width, 0),
            (page.width, 250),
            (page.width - 130, 250),
        ],
        fill=(*_REPORT_ACCENT, 230),
    )
    draw.rectangle((0, 150, page.width, 156), fill=(*_REPORT_ACCENT, 255))

    # Ornate logo watermark in the background area for branded handover feel.
    watermark_logo = _load_logo_image(meta, ("brand_logo",), int(page.width * 0.72), int(page.height * 0.24))
    if watermark_logo is not None:
        watermark = watermark_logo.copy()
        alpha = watermark.getchannel("A").point(lambda px: int(px * 0.12))
        watermark.putalpha(alpha)
        watermark_x = max(0, (page.width - int(watermark.width)) // 2)
        watermark_y = max(170, (page.height - int(watermark.height)) // 2)
        page.paste(watermark, (watermark_x, watermark_y), watermark)

    # Keep Unity logo at top priority in header.
    checklist_logo = _load_logo_image(meta, ("checklist_logo_light", "checklist_logo_dark"), 450, 92)
    brand_logo = _load_logo_image(meta, ("brand_logo",), 250, 86)

    top_margin = 24
    if checklist_logo is not None:
        page.paste(checklist_logo, (34, top_margin), checklist_logo)
    else:
        draw.text((36, 52), "UNITYESS", fill=(255, 255, 255, 255))

    if brand_logo is not None:
        right_x = max(40, int(page.width) - 40 - int(brand_logo.width))
        page.paste(brand_logo, (right_x, top_margin), brand_logo)
    else:
        draw.text((int(page.width) - 245, 52), "ORNATE SOLAR", fill=(255, 255, 255, 255))

    return 186


def _public_media_url_for_path(file_path: Path) -> str:
    media_root = Path(settings.media_root).resolve()
    relative_path = file_path.resolve().relative_to(media_root).as_posix()
    return f"/media/{relative_path}"


def _draw_wrapped_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    x: int,
    y: int,
    width_chars: int = 110,
    fill: str | tuple[int, int, int] = "black",
    line_height: int = 24,
) -> int:
    lines = textwrap.wrap(text, width=width_chars) or [text]
    for line in lines:
        draw.text((x, y), line, fill=fill)
        y += line_height
    return y


def _draw_section_banner(draw: ImageDraw.ImageDraw, title: str, x: int, y: int) -> int:
    draw.rectangle((x - 8, y - 2, x + 1080, y + 28), fill=(*_REPORT_SECTION_BG, 255))
    draw.text((x, y + 2), title, fill=_REPORT_TEXT)
    return y + 36


def _format_report_value(value: object) -> str:
    if value is None:
        return "-"
    enum_value = getattr(value, "value", None)
    if isinstance(enum_value, str):
        return enum_value
    if isinstance(value, datetime):
        return value.isoformat()
    raw = str(value).strip()
    return raw if raw else "-"


def _json_safe_value(value: object) -> object:
    enum_value = getattr(value, "value", None)
    if isinstance(enum_value, str):
        return enum_value
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _build_handover_qr_payload(
    *,
    generated_at: str,
    unit: object,
    model_number: str,
    model_capacity: str,
    country_name: str,
    city_name: str,
    warehouse_name: str,
    engineer_name: str,
    customer_name: str,
    engineer_signature_item: object | None,
    customer_signature_item: object | None,
    stage_items: list[tuple[BESSStage, list[object]]],
) -> dict[str, object]:
    stage_summary: list[dict[str, object]] = []
    for stage, items in stage_items:
        completed = sum(1 for item in items if item.is_checked)
        stage_summary.append(
            {
                "stage": stage.value,
                "total_items": len(items),
                "completed_items": completed,
                "pending_items": max(len(items) - completed, 0),
            }
        )

    return {
        "document_type": "BESS_FINAL_HANDOVER",
        "version": "1.0",
        "generated_at": generated_at,
        "bess": {
            "bess_unit_id": getattr(unit, "id", None),
            "serial_number": _format_report_value(getattr(unit, "serial_number", None)),
            "model_number": model_number,
            "model_capacity_kwh": model_capacity,
            "current_stage": _format_report_value(getattr(unit, "current_stage", None)),
            "manufactured_date": _format_report_value(getattr(unit, "manufactured_date", None)),
            "country": country_name,
            "city": city_name,
            "warehouse": warehouse_name,
            "site_address": _format_report_value(getattr(unit, "site_address", None)),
            "site_latitude": _format_report_value(getattr(unit, "site_latitude", None)),
            "site_longitude": _format_report_value(getattr(unit, "site_longitude", None)),
            "customer_user_id": _format_report_value(getattr(unit, "customer_user_id", None)),
        },
        "signatures": {
            "site_engineer": {
                "name": engineer_name,
                "signed_by_user_id": getattr(engineer_signature_item, "checked_by_user_id", None),
                "signed_at": _format_report_value(getattr(engineer_signature_item, "checked_at", None)),
            },
            "customer": {
                "name": customer_name,
                "signed_by_user_id": getattr(customer_signature_item, "checked_by_user_id", None),
                "signed_at": _format_report_value(getattr(customer_signature_item, "checked_at", None)),
            },
        },
        "stage_summary": stage_summary,
    }


def _encode_qr_payload(payload: dict[str, object]) -> str:
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=True, sort_keys=True, default=_json_safe_value)


def _generate_handover_qr(payload: dict[str, object]) -> tuple[Image.Image, dict[str, object]]:
    compact_payload = {
        "document_type": payload.get("document_type"),
        "version": payload.get("version"),
        "generated_at": payload.get("generated_at"),
        "bess": payload.get("bess"),
        "stage_summary": payload.get("stage_summary"),
    }
    minimal_payload = {
        "document_type": payload.get("document_type"),
        "version": payload.get("version"),
        "serial_number": (payload.get("bess") or {}).get("serial_number") if isinstance(payload.get("bess"), dict) else None,
        "model_number": (payload.get("bess") or {}).get("model_number") if isinstance(payload.get("bess"), dict) else None,
        "current_stage": (payload.get("bess") or {}).get("current_stage") if isinstance(payload.get("bess"), dict) else None,
        "generated_at": payload.get("generated_at"),
    }
    candidates = [payload, compact_payload, minimal_payload]

    for candidate in candidates:
        qr = QRCode(version=None, error_correction=ERROR_CORRECT_M, box_size=8, border=2)
        try:
            qr.add_data(_encode_qr_payload(candidate))
            qr.make(fit=True)
        except DataOverflowError:
            continue

        raw = qr.make_image(fill_color="black", back_color="white")
        image_obj = raw.get_image() if hasattr(raw, "get_image") else raw
        qr_image = image_obj.convert("RGB")
        qr_image.thumbnail((290, 290))
        return qr_image, candidate

    fallback = Image.new("RGB", (260, 260), "white")
    draw = ImageDraw.Draw(fallback)
    draw.rectangle((0, 0, 259, 259), outline=(30, 30, 30), width=2)
    draw.text((24, 112), "QR DATA TOO LARGE", fill=(20, 20, 20))
    return fallback, minimal_payload


def _create_report_page(
    report_title: str,
    generated_at: str,
    subtitle: str | None = None,
    page_number: int = 1,
) -> tuple[Image.Image, ImageDraw.ImageDraw, int]:
    page = Image.new("RGB", (_PAGE_WIDTH, _PAGE_HEIGHT), "white")
    draw = ImageDraw.Draw(page)
    y = _draw_report_logos(page)
    y = _draw_wrapped_text(draw, report_title, 40, y, width_chars=90, fill=_REPORT_TEXT)
    y = _draw_wrapped_text(draw, f"Generated at: {generated_at}", 40, y, width_chars=90, fill=_REPORT_TEXT)
    if subtitle:
        y = _draw_wrapped_text(draw, subtitle, 40, y, width_chars=92, fill=_REPORT_TEXT)
    draw.text((1040, 160), f"Page {page_number}", fill=(55, 55, 55))
    return page, draw, y + 8


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

    generated_at = datetime.now(UTC).isoformat()
    model_number = "-"
    if getattr(unit, "product_model", None) is not None:
        model_number = _format_report_value(getattr(unit.product_model, "model_number", None))
    country_name = _format_report_value(getattr(getattr(unit, "country", None), "name", None))
    city_name = _format_report_value(getattr(getattr(unit, "city", None), "name", None))

    pages: list[Image.Image] = []
    page_number = 1
    page, draw, y = _create_report_page(
        f"BESS Checklist Report - {_format_report_value(getattr(unit, 'serial_number', None))}",
        generated_at,
        subtitle=f"Model: {model_number} | Location: {city_name}, {country_name}",
        page_number=page_number,
    )

    for stage, items in stage_items:
        if y > 1580:
            pages.append(page)
            page_number += 1
            page, draw, y = _create_report_page(
                f"BESS Checklist Report - {_format_report_value(getattr(unit, 'serial_number', None))}",
                generated_at,
                subtitle="Checklist continuation",
                page_number=page_number,
            )
        y = _draw_section_banner(draw, f"Stage: {stage.value}", 40, y)
        y += 4
        for idx, item in enumerate(items, start=1):
            if y > 1520:
                pages.append(page)
                page_number += 1
                page, draw, y = _create_report_page(
                    f"BESS Checklist Report - {_format_report_value(getattr(unit, 'serial_number', None))}",
                    generated_at,
                    subtitle=f"Stage: {stage.value}",
                    page_number=page_number,
                )

            status = "DONE" if item.is_checked else "PENDING"
            y = _draw_wrapped_text(draw, f"{idx}. [{status}] {item.item_text}", 50, y, fill=_REPORT_TEXT)
            y = _draw_wrapped_text(draw, f"   Notes: {item.notes or '-'}", 50, y, fill=_REPORT_TEXT)
            y = _draw_wrapped_text(draw, f"   Photo: {item.photo_url or '-'}", 50, y, fill=_REPORT_TEXT)

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

    model_number = _format_report_value(getattr(getattr(unit, "product_model", None), "model_number", None))
    model_capacity = _format_report_value(getattr(getattr(unit, "product_model", None), "capacity_kwh", None))
    country_name = _format_report_value(getattr(getattr(unit, "country", None), "name", None))
    city_name = _format_report_value(getattr(getattr(unit, "city", None), "name", None))
    warehouse_name = _format_report_value(getattr(getattr(unit, "warehouse", None), "name", None))
    generated_at = datetime.now(UTC).isoformat()

    qr_payload = _build_handover_qr_payload(
        generated_at=generated_at,
        unit=unit,
        model_number=model_number,
        model_capacity=model_capacity,
        country_name=country_name,
        city_name=city_name,
        warehouse_name=warehouse_name,
        engineer_name=engineer_name,
        customer_name=customer_name,
        engineer_signature_item=engineer_signature_item,
        customer_signature_item=customer_signature_item,
        stage_items=stage_items,
    )
    qr_image, qr_payload_used = _generate_handover_qr(qr_payload)

    project_lines = [
        f"Project: BESS Site Handover",
        f"Site / Plant ID: {_format_report_value(getattr(unit, 'id', None))}",
        f"Owner / Customer: {customer_name}",
        f"OEM / EPC: UnityESS / Ornate Solar",
        f"Commissioning Date: {_format_report_value(getattr(customer_signature_item, 'checked_at', None))}",
        f"Handover Date: {_format_report_value(getattr(customer_signature_item, 'checked_at', None))}",
        f"Lead Commissioning Engineer: {engineer_name}",
    ]
    details_lines = [
        f"Serial Number: {_format_report_value(getattr(unit, 'serial_number', None))}",
        f"Model Number: {model_number}",
        f"Model Capacity (kWh): {model_capacity}",
        f"Current Stage: {_format_report_value(getattr(unit, 'current_stage', None))}",
        f"Manufactured Date: {_format_report_value(getattr(unit, 'manufactured_date', None))}",
        f"Country: {country_name}",
        f"City: {city_name}",
        f"Warehouse: {warehouse_name}",
        f"Site Address: {_format_report_value(getattr(unit, 'site_address', None))}",
        f"Site Latitude: {_format_report_value(getattr(unit, 'site_latitude', None))}",
        f"Site Longitude: {_format_report_value(getattr(unit, 'site_longitude', None))}",
        f"Customer User ID: {_format_report_value(getattr(unit, 'customer_user_id', None))}",
    ]
    compliance_lines = [
        "System compliance checked against CEA connectivity requirements and approvals.",
        "Applicable BIS / IS battery compliance and test certificates are documented.",
        "Applicable MNRE / national ESS policy and project submission documents are attached.",
    ]
    document_lines = [
        "As-built SLD and GA drawings handed over.",
        "FAT, SAT, and performance reports attached.",
        "O&M manual, emergency SOP, and warranty pack handed over.",
        "Protection settings, earthing reports, and commissioning test records verified.",
    ]
    safety_lines = [
        "Fire detection and suppression commissioning report completed.",
        "E-STOP and isolation process demonstrated at site.",
        "Site signage, access control, ventilation, and segregation verified.",
    ]
    controls_lines = [
        "EMS/SCADA telemetry and control command validation completed.",
        "Remote monitoring credentials and access rights handed over.",
        "Operator handover session completed with attendance records.",
    ]

    pages: list[Image.Image] = []
    page_number = 1
    report_title = f"Final Handover Checklist - Stationary BESS (India) - {_format_report_value(getattr(unit, 'serial_number', None))}"
    page, draw, y = _create_report_page(
        report_title,
        generated_at,
        subtitle=f"Model: {model_number} | Location: {city_name}, {country_name}",
        page_number=page_number,
    )

    def _new_page(subtitle: str) -> tuple[Image.Image, ImageDraw.ImageDraw, int, int]:
        nonlocal page_number
        pages.append(page)
        page_number += 1
        next_page, next_draw, next_y = _create_report_page(
            report_title,
            generated_at,
            subtitle=subtitle,
            page_number=page_number,
        )
        return next_page, next_draw, next_y, page_number

    def _ensure_space(current_y: int, min_space: int, subtitle: str) -> tuple[Image.Image, ImageDraw.ImageDraw, int]:
        if current_y <= (_PAGE_HEIGHT - min_space):
            return page, draw, current_y
        next_page, next_draw, next_y, _ = _new_page(subtitle)
        return next_page, next_draw, next_y

    draw.text((910, 210), "Digital Handover QR", fill=_REPORT_TEXT)
    draw.rectangle((895, 235, 1205, 545), outline=(80, 80, 80), width=2)
    page.paste(qr_image, (905, 245))
    draw.text((898, 555), "Scan for BESS handover data", fill=(45, 45, 45))
    payload_mode = "FULL" if qr_payload_used is qr_payload else "COMPACT"
    draw.text((898, 578), f"QR payload mode: {payload_mode}", fill=(45, 45, 45))

    section_blocks = [
        ("Project Information", project_lines),
        ("BESS Unit Details", details_lines),
        ("1) Regulatory and Standards Compliance", compliance_lines),
        ("2) Documentation Handed Over", document_lines),
        ("3) Safety and Site Readiness", safety_lines),
        ("4) Controls, Communication and Training", controls_lines),
    ]

    for title, lines in section_blocks:
        page, draw, y = _ensure_space(y, 120 + (len(lines) * 26), "Handover checklist continuation")
        y = _draw_section_banner(draw, title, 40, y)
        for line in lines:
            y = _draw_wrapped_text(draw, f"[x] {line}", 50, y, width_chars=95, fill=_REPORT_TEXT)
        y += 10

    page, draw, y = _ensure_space(y, 300, "Signatures and stage summary")
    y = _draw_section_banner(draw, "Signatures (Accepted)", 40, y)
    y = _draw_wrapped_text(draw, f"Site Engineer: {engineer_name}", 50, y, fill=_REPORT_TEXT)
    y = _draw_wrapped_text(
        draw,
        f"Signed At: {_format_report_value(getattr(engineer_signature_item, 'checked_at', None))}",
        50,
        y,
        fill=_REPORT_TEXT,
    )
    engineer_preview_height = _paste_photo_preview(page, engineer_signature_url, 760, max(y - 90, 50), 360, 180)
    if engineer_preview_height:
        y += engineer_preview_height
    y += 10

    y = _draw_wrapped_text(draw, f"Customer: {customer_name}", 50, y, fill=_REPORT_TEXT)
    y = _draw_wrapped_text(
        draw,
        f"Signed At: {_format_report_value(getattr(customer_signature_item, 'checked_at', None))}",
        50,
        y,
        fill=_REPORT_TEXT,
    )
    customer_preview_height = _paste_photo_preview(page, customer_signature_url, 760, max(y - 90, 50), 360, 180)
    if customer_preview_height:
        y += customer_preview_height
    y += 8

    y = _draw_section_banner(draw, "5) Functional and Stage Completion Summary", 40, y)
    for stage, items in stage_items:
        completed = sum(1 for item in items if item.is_checked)
        y = _draw_wrapped_text(
            draw,
            f"[x] {stage.value}: {completed}/{len(items)} checklist items completed",
            50,
            y,
            width_chars=95,
            fill=_REPORT_TEXT,
        )
    y += 10

    y = _draw_section_banner(draw, "References", 40, y)
    for line in _HANDOVER_REFERENCES:
        y = _draw_wrapped_text(draw, line, 50, y, width_chars=94, fill=_REPORT_TEXT)
    y += 6

    y = _draw_section_banner(draw, "Sign-Off", 40, y)
    y = _draw_wrapped_text(draw, f"Owner Representative: {customer_name}", 50, y, fill=_REPORT_TEXT)
    y = _draw_wrapped_text(draw, f"EPC/OEM Representative: {engineer_name}", 50, y, fill=_REPORT_TEXT)
    y = _draw_wrapped_text(draw, f"Commissioning Lead: {engineer_name}", 50, y, fill=_REPORT_TEXT)

    page, draw, y = _new_page("Checklist completion with photo evidence")[:3]
    y = _draw_section_banner(draw, "Checklist Completion with Photos", 40, y)
    for stage, items in stage_items:
        page, draw, y = _ensure_space(y, 120, f"Checklist stage: {stage.value}")
        y = _draw_section_banner(draw, f"Stage: {stage.value}", 40, y)
        y += 4

        for idx, item in enumerate(items, start=1):
            page, draw, y = _ensure_space(y, 160, f"Checklist stage: {stage.value}")
            status = "DONE" if item.is_checked else "PENDING"
            mandatory_label = "YES" if getattr(item, "is_mandatory", False) else "NO"
            photo_required_label = "YES" if getattr(item, "requires_photo", False) else "NO"
            y = _draw_wrapped_text(draw, f"{idx}. [{status}] {item.item_text}", 50, y, fill=_REPORT_TEXT)
            y = _draw_wrapped_text(
                draw,
                f"   Mandatory: {mandatory_label} | Photo Required: {photo_required_label}",
                50,
                y,
                width_chars=90,
                fill=_REPORT_TEXT,
            )
            y = _draw_wrapped_text(draw, f"   Notes: {item.notes or '-'}", 50, y, fill=_REPORT_TEXT)
            y = _draw_wrapped_text(draw, f"   Photo: {item.photo_url or '-'}", 50, y, width_chars=90, fill=_REPORT_TEXT)

            if item.photo_url:
                y += _paste_photo_preview(page, item.photo_url, 860, max(y - 72, 50))
            y += 8

    pages.append(page)

    report_dir = Path(settings.media_root) / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    out_file = report_dir / f"handover_document_bess_{bess_unit_id}.pdf"
    pages[0].save(out_file, "PDF", resolution=100.0, save_all=True, append_images=pages[1:])
    return out_file


async def get_handover_document_data(db: AsyncSession, bess_unit_id: int) -> HandoverDocumentDataRead:
    unit = await bess_repository.get_by_id(db, bess_unit_id)
    if unit is None or unit.is_deleted:
        raise BESSNotFoundException(bess_unit_id)

    stage_items = await _collect_stage_items(db, bess_unit_id)
    _raise_if_pending_mandatory_items(stage_items, report_label="handover document data")

    engineer_signature_item, customer_signature_item = _find_signature_items(stage_items)
    engineer_signature_url = engineer_signature_item.photo_url if engineer_signature_item else None
    customer_signature_url = customer_signature_item.photo_url if customer_signature_item else None
    if not engineer_signature_url:
        raise APIConflictException(
            "Cannot prepare handover data. Site engineer signature photo is missing in FINAL_ACCEPTANCE checklist."
        )
    if not customer_signature_url:
        raise APIConflictException(
            "Cannot prepare handover data. Customer signature photo is missing in FINAL_ACCEPTANCE checklist."
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

    branding_meta = _load_template_meta()
    stages: list[HandoverChecklistStageRead] = []
    for stage, items in stage_items:
        checklist_items = [
            HandoverChecklistItemRead(
                checklist_template_id=item.checklist_template_id,
                item_text=item.item_text,
                description=item.description,
                safety_warning=item.safety_warning,
                is_mandatory=item.is_mandatory,
                requires_photo=item.requires_photo,
                is_checked=item.is_checked,
                checked_by_user_id=item.checked_by_user_id,
                checked_at=item.checked_at,
                notes=item.notes,
                photo_url=item.photo_url,
                order_index=item.order_index,
            )
            for item in items
        ]
        completed_items = sum(1 for item in items if item.is_checked)
        stages.append(
            HandoverChecklistStageRead(
                stage=stage,
                total_items=len(items),
                completed_items=completed_items,
                items=checklist_items,
            )
        )

    model = getattr(unit, "product_model", None)
    country = getattr(unit, "country", None)
    city = getattr(unit, "city", None)
    warehouse = getattr(unit, "warehouse", None)
    generated_at = datetime.now(UTC)
    qr_payload = _build_handover_qr_payload(
        generated_at=generated_at.isoformat(),
        unit=unit,
        model_number=_format_report_value(getattr(model, "model_number", None)),
        model_capacity=_format_report_value(getattr(model, "capacity_kwh", None)),
        country_name=_format_report_value(getattr(country, "name", None)),
        city_name=_format_report_value(getattr(city, "name", None)),
        warehouse_name=_format_report_value(getattr(warehouse, "name", None)),
        engineer_name=engineer_name,
        customer_name=customer_name,
        engineer_signature_item=engineer_signature_item,
        customer_signature_item=customer_signature_item,
        stage_items=stage_items,
    )
    _, qr_payload_used = _generate_handover_qr(qr_payload)

    return HandoverDocumentDataRead(
        generated_at=generated_at,
        branding=HandoverBrandingRead(
            template_name=branding_meta.get("template_name"),
            template_version=branding_meta.get("template_version"),
            checklist_logo_dark=branding_meta.get("checklist_logo_dark"),
            checklist_logo_light=branding_meta.get("checklist_logo_light"),
            brand_logo=branding_meta.get("brand_logo"),
        ),
        bess=HandoverBESSDetailsRead(
            bess_unit_id=unit.id,
            serial_number=unit.serial_number,
            model_number=getattr(model, "model_number", None),
            model_capacity_kwh=getattr(model, "capacity_kwh", None),
            current_stage=unit.current_stage,
            manufactured_date=unit.manufactured_date,
            country=getattr(country, "name", None),
            city=getattr(city, "name", None),
            warehouse=getattr(warehouse, "name", None),
            site_address=unit.site_address,
            site_latitude=unit.site_latitude,
            site_longitude=unit.site_longitude,
            customer_user_id=unit.customer_user_id,
        ),
        signatures=[
            HandoverSignatureRead(
                role="SITE_ENGINEER",
                item_text=engineer_signature_item.item_text if engineer_signature_item else "Site Engineer Signature",
                signed_by_user_id=engineer_signature_item.checked_by_user_id if engineer_signature_item else None,
                signed_by_name=engineer_name,
                signed_at=engineer_signature_item.checked_at if engineer_signature_item else None,
                photo_url=engineer_signature_url,
            ),
            HandoverSignatureRead(
                role="CUSTOMER",
                item_text=customer_signature_item.item_text if customer_signature_item else "Customer Signature",
                signed_by_user_id=customer_signature_item.checked_by_user_id if customer_signature_item else None,
                signed_by_name=customer_name,
                signed_at=customer_signature_item.checked_at if customer_signature_item else None,
                photo_url=customer_signature_url,
            ),
        ],
        stages=stages,
        qr_payload=qr_payload_used,
    )


async def ensure_handover_document(db: AsyncSession, bess_unit_id: int) -> str:
    out_file = await export_handover_pdf(db, bess_unit_id)
    return _public_media_url_for_path(out_file)
