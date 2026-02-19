from __future__ import annotations

from datetime import UTC, datetime, timedelta

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def _create_token(subject: dict[str, object], expires_delta: timedelta, token_type: str) -> str:
    payload = subject.copy()
    expire = datetime.now(UTC) + expires_delta
    payload.update({"exp": expire, "type": token_type})
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def create_access_token(subject: dict[str, object]) -> str:
    return _create_token(
        subject=subject,
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
        token_type="access",
    )


def create_refresh_token(subject: dict[str, object]) -> str:
    return _create_token(
        subject=subject,
        expires_delta=timedelta(days=settings.refresh_token_expire_days),
        token_type="refresh",
    )


def decode_token(token: str) -> dict[str, object]:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except JWTError as exc:
        raise ValueError("Invalid token") from exc
