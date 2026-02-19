from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
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

Path(settings.media_root).mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=settings.media_root), name="media")


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": exc.errors()})


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
