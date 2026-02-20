# Testing Guide

## Run all tests

```bash
source .venv/bin/activate
pytest -q
```

## Run only fast smoke tests

```bash
source .venv/bin/activate
pytest -q tests/test_api_smoke.py tests/test_security.py
```

## Run service logic tests

```bash
source .venv/bin/activate
pytest -q tests/test_bess_unit_service.py tests/test_dependencies.py
```

## Why these tests help

- `test_security.py`: catches JWT/password regressions quickly.
- `test_dependencies.py`: catches RBAC guard behavior issues.
- `test_bess_unit_service.py`: catches stage transition logic bugs (invalid transitions, checklist checks, audit/history trigger, auto-assign trigger).
- `test_api_smoke.py`: catches route wiring regressions and auth-protection mistakes.

## Next step for deeper bug detection

Add integration tests against a dedicated PostgreSQL test DB using real migrations + seed data.
