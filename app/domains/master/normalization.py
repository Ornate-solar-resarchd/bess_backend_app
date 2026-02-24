from __future__ import annotations

import re

HESS_PATTERN = re.compile(r"\bHESS\b", flags=re.IGNORECASE)
IEC_KEY_PATTERN = re.compile(r"^iec(_designation)?$")


def normalize_hess_to_uess(value: str) -> str:
    return HESS_PATTERN.sub("UESS", value)


def normalize_spec_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", key.strip().lower()).strip("_")


def build_product_description(
    base_description: str | None,
    spec_fields: dict[str, str] | None,
) -> str | None:
    lines: list[str] = []

    if base_description:
        base = normalize_hess_to_uess(base_description.strip())
        if base:
            lines.append(base)

    if spec_fields:
        for raw_key, raw_value in spec_fields.items():
            key = normalize_spec_key(raw_key)
            if not key or IEC_KEY_PATTERN.match(key):
                continue
            value = normalize_hess_to_uess(str(raw_value).strip())
            if not value:
                continue
            pretty_key = key.replace("_", " ").title()
            lines.append(f"{pretty_key}: {value}")

    if not lines:
        return None
    return "\n".join(lines)
