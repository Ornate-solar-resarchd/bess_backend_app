# Unity BESS Backend: Setup and API Flow Guide

## 1. Environment Setup (venv + dependencies)

```bash
# from project root
/opt/homebrew/bin/python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Verify:

```bash
python -V
pip check
```

## 2. Run the system

```bash
# API
source .venv/bin/activate
uvicorn app.main:app --reload

# Celery worker (new terminal)
source .venv/bin/activate
celery -A app.workers.celery_app.celery_app worker -l info
```

Database bootstrap:

```bash
source .venv/bin/activate
alembic upgrade head
PYTHONPATH=. python scripts/seed.py
PYTHONPATH=. python scripts/seed_demo_data.py
```

## 3. Demo data for frontend

Use these login users (already inserted):

- `admin@bess.local / ChangeMe123!`
- `factory.demo@bess.com / Factory@123`
- `logistics.demo@bess.com / Logistics@123`
- `customer.demo@bess.com / Customer@123`

Demo BESS units (already inserted):

- `DEMO-BESS-001` -> `FACTORY_REGISTERED`
- `DEMO-BESS-002` -> `IN_TRANSIT`
- `DEMO-BESS-003` -> `SITE_ARRIVED` (checklist partially completed)
- `DEMO-BESS-004` -> `PRE_COMMISSION` (checklist in progress)

Demo shipment:

- `DEMO-SHP-001` -> `IN_TRANSIT`

## 4. Authentication flow

1. Register user
- `POST /api/v1/auth/register`

2. Login
- `POST /api/v1/auth/login`
- Response gives `access_token` + `refresh_token`

3. Refresh access token
- `POST /api/v1/auth/refresh`

Use token in all protected APIs:

```http
Authorization: Bearer <access_token>
```

## 5. Full lifecycle flow (step-by-step)

### Step 1: Master data creation

1. Create country
- `POST /api/v1/master/countries`

2. Create city
- `POST /api/v1/master/cities`

3. Create warehouse
- `POST /api/v1/master/warehouses`

4. Create product model
- `POST /api/v1/master/product-models`
- Use `spec_fields` to send full nameplate details; backend stores them in `description`.
- `iec_designation` is automatically excluded from stored description.
- If `HESS` appears in model/details, backend converts it to `UESS`.

### Step 2: Factory registration (existing hardware QR-first)

Use this when box already has factory QR and serial from manufacturer.

1. Parse raw QR text from scanner
- `POST /api/v1/bess/qr/parse`
- Send scanner output exactly as-is in `qr_raw_data`
- Backend extracts `serial_number`, `model_number`, `manufactured_date`
- QR model values containing `HESS` are normalized to `UESS`.

Example:

```json
{
  "qr_raw_data": "Product Model: UESS-215-418-EU-IN\nMade Date: 2026.1\nFactory Code: EESB2LFPL8001331215418260001"
}
```

2. Register BESS from QR payload
- `POST /api/v1/bess/register-from-qr`
- Uses detected serial from QR (no new serial generated)
- Does not regenerate QR PNG
- `warehouse_id` must be `null` at factory registration
- If product model is not found, backend auto-creates it from parsed model + capacity fields.
- You can still pass `product_model_id` to force mapping.

Example:

```json
{
  "qr_raw_data": "Product Model: UESS-215-418-EU-IN\nMade Date: 2026.1\nFactory Code: EESB2LFPL8001331215418260001",
  "product_model_id": 1,
  "existing_qr_code_url": "https://vendor.example/qr/EESB2LFPL8001331215418260001",
  "country_id": 1,
  "city_id": 1,
  "warehouse_id": null,
  "site_address": "Plant-1"
}
```

2B. Register BESS directly from photo (no QR text needed)
- `POST /api/v1/bess/register-from-photo` (multipart/form-data)
- Required form fields: `photo`, `country_id`, `city_id`
- Optional: `product_model_id`, `serial_number_override`, `manufactured_date`, `ocr_text_override`
- Backend runs OCR, parses serial/model/date, stores photo at `/media/nameplates/...`, and saves URL in `nameplate_photo_url`
- If parsed model is not found, backend auto-creates product model from parsed details.

3. Public QR scan endpoint
- `GET /api/v1/bess/scan/{serial_number}`
- No auth required

4. Download QR file (only when backend-generated PNG exists)
- `GET /api/v1/bess/{id}/qrcode`

### Step 3: Shipment/container flow (multi-BESS)

This is the China -> India container use case.

1. Create one shipment (container) with expected quantity
- `POST /api/v1/shipments/`

Example:

```json
{
  "shipment_code": "CN-IN-2026-001",
  "origin_country_id": 1,
  "destination_country_id": 2,
  "created_date": "2026-02-24",
  "expected_arrival_date": "2026-03-02",
  "expected_quantity": 20
}
```

2. Add BESS units into this shipment
- Single add: `POST /api/v1/shipments/{id}/units`
- Bulk add: `POST /api/v1/shipments/{id}/units/bulk`
- Each item must have `order_id` (for PO/container traceability)
- One BESS can be linked to only one shipment globally (409 if already linked elsewhere)
- BESS stage moves to `SHIPMENT_ASSIGNED`

Single add example:

```json
{
  "bess_unit_id": 12,
  "order_id": "PO-UNITY-0001"
}
```

Bulk add example:

```json
{
  "items": [
    { "bess_unit_id": 12, "order_id": "PO-UNITY-0001" },
    { "bess_unit_id": 13, "order_id": "PO-UNITY-0001" }
  ]
}
```

3. Upload shipment documents (Bill of Lading, Invoice, Packing List, etc.)
- `POST /api/v1/shipments/{id}/documents/upload` (multipart/form-data)
- `GET /api/v1/shipments/{id}/documents?page=1&size=20`

Local storage path:
- Files are saved under `MEDIA_ROOT/shipment_documents/{shipment_id}/...`
- Public URL is stored as `/media/shipment_documents/{shipment_id}/...`

4. Verify shipment mapping
- `GET /api/v1/shipments/{id}/units?page=1&size=20`
- Use response `total` as actual assigned quantity.

4B. Fetch full shipment detail in one API call
- `GET /api/v1/shipments/{id}`
- Returns:
  - shipment header (`shipment_code`, `status`, `expected_quantity`, etc.)
  - all shipment units with `order_id`
  - all uploaded shipment documents

5. Update shipment status
- `PATCH /api/v1/shipments/{id}/status`
- Rules:
  - To set `PACKED`, backend enforces:
    - `assigned_units >= expected_quantity`
    - at least 1 shipment document uploaded
  - `PACKED` -> BESS `PACKED`
  - `IN_TRANSIT` -> BESS `IN_TRANSIT`
  - `ARRIVED` -> BESS `PORT_ARRIVED`

5B. Fetch all shipments linked to one BESS
- `GET /api/v1/bess/{bess_unit_id}/shipments?page=1&size=20`
- Returns shipment linkage rows for that BESS (normally max 1 because of one-BESS-one-shipment rule):
  - `shipment_id`
  - `shipment_code`
  - `shipment_status`
  - `order_id`
  - `linked_at`

### Step 4: Checklist + stage transition at site

1. Read checklist for a stage
- `GET /api/v1/bess/{id}/checklist/{stage}`

2. Mark checklist item checked/unchecked
- `PATCH /api/v1/bess/{id}/checklist/{item_id}`
- Photo upload is mandatory for every checked checklist item.
- If `photo_url` is missing when `is_checked=true`, backend returns HTTP `400`.

3. Validate checklist completeness
- `POST /api/v1/bess/{id}/checklist/{stage}/validate`

4. Transition stage
- `PATCH /api/v1/bess/{id}/transition`
- Transition is allowed only to the exact next stage.
- Mandatory checklist items for current stage must be complete.
- Writes `stage_history` + `audit_logs` atomically.

5. View stage history
- `GET /api/v1/bess/{id}/history`

6. Download final checklist report (PDF)
- `GET /api/v1/bess/{id}/checklist-report/pdf`
- PDF is available only after all mandatory checklist items are complete.

### Step 4B: Logistics stage certificates

For key logistics stages, certificate upload is required before next transition:
- `PORT_ARRIVED`
- `PORT_CLEARED`
- `WAREHOUSE_STORED`

APIs:
- Add certificate: `POST /api/v1/bess/{id}/certificates`
- List certificates: `GET /api/v1/bess/{id}/certificates?stage=PORT_ARRIVED&page=1&size=20`

If missing certificate at required logistics stage, transition API returns HTTP `400`.

### Step 5: Engineer assignment flow

1. Create engineer profile
- `POST /api/v1/engineers/`

2. List available engineers
- `GET /api/v1/engineers/available?city_id=&stage=`

3. Manual assignment
- `POST /api/v1/bess/{id}/assign-engineer`

4. Get BESS assignments
- `GET /api/v1/bess/{id}/assignments`

5. Engineer views own assignments
- `GET /api/v1/engineers/my-assignments`

6. Engineer actions
- Accept: `PATCH /api/v1/assignments/{id}/accept`
- Decline: `PATCH /api/v1/assignments/{id}/decline` (auto reassign task triggered)
- Complete: `PATCH /api/v1/assignments/{id}/complete` (next-stage auto-assign if needed)

### Step 6: Commissioning records

1. Create commissioning record
- `POST /api/v1/commissioning/{bess_unit_id}/records`

2. List commissioning records
- `GET /api/v1/commissioning/{bess_unit_id}/records`

### Step 7: Reports

1. Stage distribution report
- `GET /api/v1/reports/`

## 8. Non-technical flow (what actually happens)

1. Factory scans each box QR and registers unit in system.
2. Logistics creates one shipment for one container and sets how many BESS are expected.
3. Logistics links many BESS units to that shipment (one by one or bulk).
4. Logistics uploads container documents.
5. Shipment moves through statuses (`PACKED`, `IN_TRANSIT`, `ARRIVED`).
6. At each site/installation stage, installer fills checklist items and uploads mandatory photos.
7. Only after checklist completion can stage move to next stage.
8. Engineering assignment happens for site stages.
9. Commissioning records are added.
10. Final checklist PDF/report is generated and downloaded.

## 6. Core permission mapping (quick reference)

- BESS create: `bess:create`
- BESS read: `bess:read`
- Stage transition: `bess:transition`
- Checklist read/write: `checklist:read`, `checklist:write`
- Shipment manage/read: `shipment:manage`, `shipment:read`
- Engineer assign/read: `engineer:assign`, `engineer:read`
- Master write/read: `master:write`, `master:read`
- Reports: `report:view`
- Super admin role management: `SUPER_ADMIN`

## 7. Recommended API execution order for UAT

1. `POST /api/v1/auth/login` (admin)
2. `POST /api/v1/master/countries`
3. `POST /api/v1/master/cities`
4. `POST /api/v1/master/warehouses`
5. `POST /api/v1/master/product-models`
6. `POST /api/v1/bess/`
7. `POST /api/v1/shipments/`
8. `POST /api/v1/shipments/{id}/units` or `/units/bulk`
9. `POST /api/v1/shipments/{id}/documents/upload`
10. `GET /api/v1/shipments/{id}` (full shipment detail)
11. `PATCH /api/v1/shipments/{id}/status` (PACKED/IN_TRANSIT/ARRIVED)
12. Checklist APIs + `PATCH /api/v1/bess/{id}/transition` for each stage
13. Engineer assignment APIs
14. Commissioning APIs
15. `GET /api/v1/reports/`
