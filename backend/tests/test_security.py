import jwt
import pytest

from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


def test_password_hash() -> None:
    hashed = hash_password("password")
    assert verify_password("password", hashed)


def test_fail_password_hash() -> None:
    hashed = hash_password("password")
    assert not verify_password("wrong_password", hashed)


def test_hash_different_from_password() -> None:
    hs = hash_password("password")
    assert hs != "password"


def test_same_password_produces_different_hashes() -> None:
    first = hash_password("password")
    second = hash_password("password")

    assert first != second
    assert verify_password("password", first)
    assert verify_password("password", second)


def test_verify_token() -> None:
    token = create_access_token("user-123")
    payload = decode_token(token)
    assert payload["sub"] == "user-123"
    assert payload["type"] == "access"


def test_refresh_token_type() -> None:
    token = create_refresh_token("user-123")
    payload = decode_token(token)
    assert payload["sub"] == "user-123"
    assert payload["type"] == "refresh"


def test_expired_token_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "access_token_expire_minutes", -1)
    token = create_access_token("user-123")
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_token(token)


def test_tampered_token_raise() -> None:
    token = create_access_token("user-123")
    with pytest.raises(jwt.InvalidTokenError):
        decode_token(token + "X")
