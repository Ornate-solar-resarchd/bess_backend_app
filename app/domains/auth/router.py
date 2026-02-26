from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.domains.auth import service
from app.domains.auth.schemas import (
    AuthResponse,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserRead,
)
from app.shared.exceptions import APIValidationException

router = APIRouter(prefix="/auth", tags=["Auth"])


async def _parse_login_request(request: Request) -> LoginRequest:
    content_type = (request.headers.get("content-type") or "").lower()
    if "application/json" in content_type:
        payload = await request.json()
        return LoginRequest.model_validate(payload)

    form = await request.form()
    email_or_username = form.get("email") or form.get("username")
    password = form.get("password")
    if not email_or_username or not password:
        raise APIValidationException("email/username and password are required")

    return LoginRequest(email=str(email_or_username), password=str(password))


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)) -> AuthResponse:
    user = await service.register_user(db, payload)
    tokens = await service.issue_tokens(db, user)
    return AuthResponse(user=UserRead.model_validate(user), tokens=tokens)


@router.post("/login", response_model=TokenResponse)
async def login(request: Request, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    payload = await _parse_login_request(request)
    user = await service.authenticate(db, payload)
    return await service.issue_tokens(db, user)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(payload: RefreshRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    return await service.refresh_tokens(db, payload.refresh_token)
