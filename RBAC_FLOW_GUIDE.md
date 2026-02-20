# RBAC Flow Guide

This project uses both:
- `permission` guards (`require_permission("...")`)
- `role` guards (`require_role("SUPER_ADMIN")`)

## Seed RBAC Data

Run:

```bash
PYTHONPATH=. ./.venv/bin/python scripts/seed_rbac_flow.py
```

What it seeds (idempotent):
- 14 permissions
- 6 roles
- role-permission mappings
- 6 demo users (one per role), password: `RoleDemo@123`

## Public Endpoints

- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/refresh`
- `GET /api/v1/bess/scan/{serial_number}`

## Role-Only Endpoints

These are guarded by role, not by permission:
- `GET /api/v1/admin/roles` (`SUPER_ADMIN`)
- `POST /api/v1/admin/roles` (`SUPER_ADMIN`)
- `POST /api/v1/admin/users/{user_id}/roles` (`SUPER_ADMIN`)
- `DELETE /api/v1/admin/users/{user_id}/roles/{role_id}` (`SUPER_ADMIN`)

## Permission -> Endpoints

- `bess:create`
  - `POST /api/v1/bess/`
  - `PATCH /api/v1/bess/{bess_unit_id}`
- `bess:read`
  - `GET /api/v1/bess/`
  - `GET /api/v1/bess/{bess_unit_id}`
  - `GET /api/v1/bess/{bess_unit_id}/qrcode`
  - `GET /api/v1/bess/{bess_unit_id}/history`
  - `GET /api/v1/commissioning/{bess_unit_id}/records`
- `bess:transition`
  - `PATCH /api/v1/bess/{bess_unit_id}/transition`
  - `POST /api/v1/commissioning/{bess_unit_id}/records`
- `checklist:read`
  - `GET /api/v1/bess/{bess_unit_id}/checklist/{stage}`
  - `POST /api/v1/bess/{bess_unit_id}/checklist/{stage}/validate`
- `checklist:write`
  - `PATCH /api/v1/bess/{bess_unit_id}/checklist/{item_id}`
- `engineer:assign`
  - `POST /api/v1/bess/{bess_unit_id}/assign-engineer`
- `engineer:read`
  - `GET /api/v1/engineers/available`
  - `GET /api/v1/engineers/my-assignments`
  - `GET /api/v1/bess/{bess_unit_id}/assignments`
  - `PATCH /api/v1/assignments/{assignment_id}/accept`
  - `PATCH /api/v1/assignments/{assignment_id}/decline`
  - `PATCH /api/v1/assignments/{assignment_id}/complete`
- `shipment:manage`
  - `POST /api/v1/shipments/`
  - `POST /api/v1/shipments/{shipment_id}/units`
  - `PATCH /api/v1/shipments/{shipment_id}/status`
- `shipment:read`
  - `GET /api/v1/shipments/`
- `master:write`
  - `POST /api/v1/master/countries`
  - `POST /api/v1/master/cities`
  - `POST /api/v1/master/warehouses`
  - `POST /api/v1/master/product-models`
- `master:read`
  - `GET /api/v1/master/countries`
  - `GET /api/v1/master/cities`
  - `GET /api/v1/master/warehouses`
  - `GET /api/v1/master/product-models`
- `report:view`
  - `GET /api/v1/reports/`
- `user:manage`
  - `POST /api/v1/engineers/`

Currently not used as direct permission guard:
- `role:manage` (RBAC admin APIs use `SUPER_ADMIN` role guard)

## Roles Summary

- `SUPER_ADMIN`: all permissions + RBAC admin role-only APIs
- `FACTORY_ADMIN`: create/read BESS, shipment manage, master read/write
- `LOGISTICS_OPS`: shipment manage/read, BESS read/transition
- `SITE_ENGINEER`: BESS read/transition, checklist read/write, engineer read
- `QA_INSPECTOR`: checklist read, BESS read, report view
- `CUSTOMER`: BESS read, report view (BESS list filtered to own units)

