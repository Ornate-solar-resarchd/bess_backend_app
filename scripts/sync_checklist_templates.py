from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.domains.installation.models import ChecklistTemplate
from app.domains.installation.template_loader import load_checklist_templates
from app.shared.acid import atomic


async def sync_checklist_templates() -> None:
    templates = load_checklist_templates()
    created = 0
    updated = 0

    async with AsyncSessionLocal() as db:
        async with atomic(db) as session:
            for stage, items in templates.items():
                for order_idx, item in enumerate(items):
                    existing = await session.scalar(
                        select(ChecklistTemplate).where(
                            ChecklistTemplate.stage == stage,
                            ChecklistTemplate.item_text == str(item["item_text"]),
                        )
                    )
                    if existing is None:
                        session.add(
                            ChecklistTemplate(
                                stage=stage,
                                item_text=str(item["item_text"]),
                                description=item.get("description"),
                                safety_warning=item.get("safety_warning"),
                                is_mandatory=bool(item.get("is_mandatory", True)),
                                requires_photo=bool(item.get("requires_photo", False)),
                                order_index=order_idx,
                            )
                        )
                        created += 1
                        continue

                    changed = False
                    for field, value in (
                        ("description", item.get("description")),
                        ("safety_warning", item.get("safety_warning")),
                        ("is_mandatory", bool(item.get("is_mandatory", True))),
                        ("requires_photo", bool(item.get("requires_photo", False))),
                        ("order_index", order_idx),
                    ):
                        if getattr(existing, field) != value:
                            setattr(existing, field, value)
                            changed = True
                    if changed:
                        updated += 1
            await session.flush()

    print(f"Checklist templates synced. created={created}, updated={updated}")


if __name__ == "__main__":
    asyncio.run(sync_checklist_templates())
