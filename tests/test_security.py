from __future__ import annotations

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_password_hash,
    verify_password,
)


def test_password_hash_and_verify() -> None:
    password = "Admin@1234"
    hashed = get_password_hash(password)

    assert hashed != password
    assert verify_password(password, hashed) is True
    assert verify_password("WrongPassword", hashed) is False


def test_access_token_payload_has_expected_claims() -> None:
    token = create_access_token(
        {
            "sub": "1",
            "email": "admin@bess.com",
            "roles": ["SUPER_ADMIN"],
            "permissions": ["bess:read"],
        }
    )
    payload = decode_token(token)

    assert payload["sub"] == "1"
    assert payload["type"] == "access"
    assert "exp" in payload


def test_refresh_token_payload_has_expected_claims() -> None:
    token = create_refresh_token(
        {
            "sub": "1",
            "email": "admin@bess.com",
            "roles": ["SUPER_ADMIN"],
            "permissions": ["bess:read"],
        }
    )
    payload = decode_token(token)

    assert payload["sub"] == "1"
    assert payload["type"] == "refresh"
    assert "exp" in payload
