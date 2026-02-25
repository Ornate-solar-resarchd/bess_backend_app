# Checklist Template Guide (Manual-Based)

Your installation checklist templates now live in:

- `app/domains/installation/templates/unity_manual_checklists.json`

This file is the single source for stage checklists taken from your installation manual.

Optional metadata is also supported via keys that start with `_` (for example `_meta`).
This can be used for template branding values such as logo paths without breaking checklist sync.

## How to update templates

1. Open `app/domains/installation/templates/unity_manual_checklists.json`
2. Edit items under the correct stage key (for example `CIVIL_INSTALLATION`)
3. Keep fields:
   - `item_text` (required)
   - `description` (optional)
   - `safety_warning` (optional)
   - `is_mandatory` (true/false)
   - `requires_photo` (true/false)

Example metadata block:

```json
"_meta": {
  "template_name": "Unity Manual Checklist",
  "checklist_logo_dark": "docs/assets/unityess-logo-dark.png",
  "brand_logo": "docs/assets/ornate-solar-logo.png"
}
```

## Apply changes to database

```bash
source .venv/bin/activate
PYTHONPATH=. python scripts/sync_checklist_templates.py
```

Or full seed:

```bash
source .venv/bin/activate
PYTHONPATH=. python scripts/seed.py
```

## Frontend usage

For any BESS stage, frontend should call:

- `GET /api/v1/bess/{id}/checklist/{stage}`

It returns template + checked/unchecked response state in one payload.
