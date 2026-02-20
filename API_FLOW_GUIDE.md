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

### Step 2: Factory registration (scan box data or auto-generate)

1. Create BESS unit
- `POST /api/v1/bess/`
- You can use either mode:
  - **Scan/register mode (recommended for real hardware):** send scanned `serial_number`, set `regenerate_qr_png=false`, optionally send `existing_qr_code_url`
  - **Auto mode:** skip `serial_number`, keep `regenerate_qr_png=true` and backend generates serial + QR PNG

Example (scan/register mode):

```json
{
  "serial_number": "BESS-BOX-00091",
  "existing_qr_code_url": "https://vendor.example/qr/BESS-BOX-00091",
  "regenerate_qr_png": false,
  "product_model_id": 1,
  "country_id": 1,
  "city_id": 1,
  "warehouse_id": 1,
  "site_address": "Plant-1"
}
```

2. Public QR scan endpoint
- `GET /api/v1/bess/scan/{serial_number}`
- No auth required

3. Download QR file
- `GET /api/v1/bess/{id}/qrcode`

### Step 3: Shipment flow

1. Create shipment
- `POST /api/v1/shipments/`

2. Assign BESS to shipment
- `POST /api/v1/shipments/{id}/units`
- BESS stage moves to `SHIPMENT_ASSIGNED`

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

3. Validate checklist completeness
- `POST /api/v1/bess/{id}/checklist/{stage}/validate`

4. Transition stage
- `PATCH /api/v1/bess/{id}/transition`
- Transition is allowed only to the exact next stage.
- Mandatory checklist items for current stage must be complete.
- Writes `stage_history` + `audit_logs` atomically.

5. View stage history
- `GET /api/v1/bess/{id}/history`

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
