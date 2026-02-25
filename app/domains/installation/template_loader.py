from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.shared.enums import BESSStage
from app.shared.exceptions import APIValidationException


DEFAULT_TEMPLATE_PATH = Path("app/domains/installation/templates/unity_manual_checklists.json")


def _is_metadata_key(key: str) -> bool:
    # Allow template-level metadata blocks such as "_meta" without treating them as stages.
    return key.startswith("_")


def load_checklist_templates(path: Path | None = None) -> dict[BESSStage, list[dict[str, Any]]]:
    template_path = path or DEFAULT_TEMPLATE_PATH
    if not template_path.exists():
        raise APIValidationException(f"Checklist template file not found: {template_path}")

    raw = json.loads(template_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise APIValidationException("Checklist template file must be a JSON object of stage -> items")

    checklist_map: dict[BESSStage, list[dict[str, Any]]] = {}
    for stage_name, items in raw.items():
        if _is_metadata_key(stage_name):
            continue

        try:
            stage = BESSStage(stage_name)
        except ValueError as exc:
            raise APIValidationException(f"Invalid checklist stage in template file: {stage_name}") from exc

        if not isinstance(items, list):
            raise APIValidationException(f"Checklist stage '{stage_name}' must contain a list of items")

        normalized_items: list[dict[str, Any]] = []
        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                raise APIValidationException(f"Checklist item #{idx + 1} in stage '{stage_name}' must be an object")

            item_text = str(item.get("item_text", "")).strip()
            if not item_text:
                raise APIValidationException(f"Checklist item #{idx + 1} in stage '{stage_name}' is missing item_text")

            normalized_items.append(
                {
                    "item_text": item_text,
                    "description": str(item.get("description")).strip() if item.get("description") else None,
                    "safety_warning": (
                        str(item.get("safety_warning")).strip() if item.get("safety_warning") else None
                    ),
                    "is_mandatory": bool(item.get("is_mandatory", True)),
                    "requires_photo": bool(item.get("requires_photo", False)),
                }
            )

        checklist_map[stage] = normalized_items

    if not checklist_map:
        raise APIValidationException("Checklist template file must contain at least one valid checklist stage")

    return checklist_map
