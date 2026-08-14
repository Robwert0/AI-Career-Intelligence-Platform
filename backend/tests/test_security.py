import string
from datetime import UTC, datetime

import jwt
import pytest

from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)


def test_long_password_raise() -> None:
    with pytest.raises(ValueError):
        hash_password("x" * 73)


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
    payload = decode_token(token, expected_type="access")
    assert payload["sub"] == "user-123"
    assert payload["type"] == "access"


def test_refresh_token_type() -> None:
    token = create_refresh_token("user-123")
    payload = decode_token(token, expected_type="refresh")
    assert payload["sub"] == "user-123"
    assert payload["type"] == "refresh"


def test_expired_token_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "access_token_expire_minutes", -1)
    token = create_access_token("user-123")
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_token(token, expected_type="access")


def test_tampered_token_raise() -> None:
    token = create_access_token("user-123")
    with pytest.raises(jwt.InvalidTokenError):
        decode_token(token + "X", expected_type="access")


def test_refresh_token_rejected_as_access() -> None:
    token = create_refresh_token("user-123")
    with pytest.raises(jwt.InvalidTokenError):
        decode_token(token, expected_type="access")


def test_access_token_rejected_as_refresh() -> None:
    token = create_access_token("user-123")
    with pytest.raises(jwt.InvalidTokenError):
        decode_token(token, expected_type="refresh")


def test_generated_tokens_are_unique() -> None:
    assert generate_refresh_token() != generate_refresh_token()


def test_generated_token_is_url_safe_and_long() -> None:
    token = generate_refresh_token()

    assert len(token) >= 43
    assert set(token) <= set(string.ascii_letters + string.digits + "-_")


def test_hashing_is_deterministic() -> None:
    token = generate_refresh_token()

    assert hash_refresh_token(token) == hash_refresh_token(token)


def test_hash_is_sha256_hex_and_not_the_token() -> None:
    token = generate_refresh_token()
    hashed = hash_refresh_token(token)

    assert len(hashed) == 64
    assert int(hashed, 16) >= 0
    assert hashed != token


def test_different_tokens_hash_differently() -> None:
    assert hash_refresh_token("token-a") != hash_refresh_token("token-b")


def test_token_missing_exp_rejected() -> None:
    forged = jwt.encode(
        {
            "sub": "user-123",
            "type": "access",
            "iat": datetime.now(UTC),
        },
        settings.secret_key,
        algorithm="HS256",
    )
    with pytest.raises(jwt.InvalidTokenError):
        decode_token(forged, expected_type="access")
