from __future__ import annotations

import json

import pytest

from app.domains.installation.template_loader import load_checklist_templates
from app.shared.enums import BESSStage
from app.shared.exceptions import APIValidationException


def test_load_checklist_templates_ignores_meta_section(tmp_path) -> None:
    payload = {
        "_meta": {
            "template_name": "Unity Manual Checklist",
            "checklist_logo_dark": "docs/assets/unityess-logo-dark.png",
        },
        "SITE_ARRIVED": [
            {
                "item_text": "Inspect unit for physical damage",
                "is_mandatory": True,
                "requires_photo": True,
            }
        ],
    }
    file_path = tmp_path / "checklists.json"
    file_path.write_text(json.dumps(payload), encoding="utf-8")

    result = load_checklist_templates(file_path)

    assert BESSStage.SITE_ARRIVED in result
    assert len(result[BESSStage.SITE_ARRIVED]) == 1


def test_load_checklist_templates_requires_at_least_one_stage(tmp_path) -> None:
    payload = {
        "_meta": {
            "template_name": "Unity Manual Checklist",
            "checklist_logo_dark": "docs/assets/unityess-logo-dark.png",
        }
    }
    file_path = tmp_path / "checklists.json"
    file_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(APIValidationException):
        load_checklist_templates(file_path)
