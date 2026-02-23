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

### Step 2: Factory registration (existing hardware QR-first)

Use this when box already has factory QR and serial from manufacturer.

1. Parse raw QR text from scanner
- `POST /api/v1/bess/qr/parse`
- Send scanner output exactly as-is in `qr_raw_data`
- Backend extracts `serial_number`, `model_number`, `manufactured_date`

Example:

```json
{
  "qr_raw_data": "Product Model: HESS-215-418-EU-IN\nMade Date: 2026.1\nFactory Code: EESB2LFPL8001331215418260001"
}
```

2. Register BESS from QR payload
- `POST /api/v1/bess/register-from-qr`
- Uses detected serial from QR (no new serial generated)
- Does not regenerate QR PNG
- `warehouse_id` must be `null` at factory registration
- If product model not resolvable from QR, pass `product_model_id`

Example:

```json
{
  "qr_raw_data": "Product Model: HESS-215-418-EU-IN\nMade Date: 2026.1\nFactory Code: EESB2LFPL8001331215418260001",
  "product_model_id": 1,
  "existing_qr_code_url": "https://vendor.example/qr/EESB2LFPL8001331215418260001",
  "country_id": 1,
  "city_id": 1,
  "warehouse_id": 1,
  "site_address": "Plant-1"
}
```

3. Public QR scan endpoint
- `GET /api/v1/bess/scan/{serial_number}`
- No auth required

4. Download QR file (only when backend-generated PNG exists)
- `GET /api/v1/bess/{id}/qrcode`

### Step 3: Shipment flow

1. Create shipment
- `POST /api/v1/shipments/`

2. Assign BESS to shipment
- `POST /api/v1/shipments/{id}/units`
- Payload must include `order_id` to bind BESS to purchase/order/container reference.
- BESS stage moves to `SHIPMENT_ASSIGNED`

Example:

```json
{
  "bess_unit_id": 12,
  "order_id": "PO-UNITY-0001"
}
```

2B. List shipment units with order mapping
- `GET /api/v1/shipments/{id}/units?page=1&size=20`

3. Update shipment status
- `PATCH /api/v1/shipments/{id}/status`
- `PACKED` -> BESS `PACKED`
- `IN_TRANSIT` -> BESS `IN_TRANSIT`
- `ARRIVED` -> BESS `PORT_ARRIVED`

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
8. `POST /api/v1/shipments/{id}/units`
9. `PATCH /api/v1/shipments/{id}/status` (PACKED/IN_TRANSIT/ARRIVED)
10. Checklist APIs + `PATCH /api/v1/bess/{id}/transition` for each stage
11. Engineer assignment APIs
12. Commissioning APIs
13. `GET /api/v1/reports/`
