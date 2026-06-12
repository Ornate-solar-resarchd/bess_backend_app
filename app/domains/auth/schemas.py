from __future__ import annotations

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str = Field(min_length=1, max_length=255)
    phone: str | None = None


class LoginRequest(BaseModel):
    # Plain str, not EmailStr: strict format validation belongs at registration.
    # At login we only compare against stored emails — a malformed address
    # (e.g. "admin@bess" instead of "admin@bess.com") should produce a clean
    # "Invalid email or password", not a 500 from pydantic validation.
    email: str = Field(min_length=1, max_length=255)
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    full_name: str
    phone: str | None
    is_active: bool
    is_verified: bool


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class AuthResponse(BaseModel):
    user: UserRead
    tokens: TokenResponse


class MeResponse(BaseModel):
    user: UserRead
    roles: list[str]
    permissions: list[str]


class LoginResponse(BaseModel):
    user: UserRead
    roles: list[str]
    permissions: list[str]
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
