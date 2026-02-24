from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.database import init_models
from app.domains.auth.router import router as auth_router
from app.domains.bess_unit.router import router as bess_router
from app.domains.commissioning.router import router as commissioning_router
from app.domains.engineer.router import router as engineer_router
from app.domains.installation.router import router as installation_router
from app.domains.master.router import router as master_router
from app.domains.rbac.router import router as rbac_router
from app.domains.reports.router import router as reports_router
from app.domains.shipment.router import router as shipment_router
from app.domains.uploads.router import router as uploads_router

try:
    from app.admin import setup_admin
except ModuleNotFoundError:
    setup_admin = None
try:
    from starlette.middleware.sessions import SessionMiddleware
except ModuleNotFoundError:
    SessionMiddleware = None

@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_models()
    yield


app = FastAPI(title=settings.project_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
if SessionMiddleware is not None:
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key,
        session_cookie="bess_admin_session",
        max_age=60 * 60 * 8,
    )

Path(settings.media_root).mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=settings.media_root), name="media")


def _make_json_safe(value: Any) -> Any:
    if isinstance(value, bytes):
        return f"<{len(value)} bytes binary>"
    if isinstance(value, dict):
        return {key: _make_json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_make_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_make_json_safe(item) for item in value)
    return value


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    safe_errors = _make_json_safe(exc.errors())
    return JSONResponse(status_code=422, content=jsonable_encoder({"detail": safe_errors}))


@app.exception_handler(Exception)
async def unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=500, content={"detail": str(exc)})


app.include_router(auth_router, prefix=settings.api_v1_prefix)
app.include_router(rbac_router, prefix=settings.api_v1_prefix)
app.include_router(master_router, prefix=settings.api_v1_prefix)
app.include_router(bess_router, prefix=settings.api_v1_prefix)
app.include_router(installation_router, prefix=settings.api_v1_prefix)
app.include_router(shipment_router, prefix=settings.api_v1_prefix)
app.include_router(commissioning_router, prefix=settings.api_v1_prefix)
app.include_router(engineer_router, prefix=settings.api_v1_prefix)
app.include_router(reports_router, prefix=settings.api_v1_prefix)
app.include_router(uploads_router, prefix=settings.api_v1_prefix)

if setup_admin is not None and SessionMiddleware is not None:
    setup_admin(app, secret_key=settings.secret_key)
