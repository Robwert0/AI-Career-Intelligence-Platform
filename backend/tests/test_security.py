import hashlib
import string
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_login_device_token,
    decode_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    login_account_key,
    login_device_id,
    verify_password,
)


def mint_refresh_jwt() -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {"sub": "user-123", "type": "refresh", "iat": now, "exp": now + timedelta(days=1)},
        settings.secret_key,
        algorithm="HS256",
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
    with pytest.raises(jwt.InvalidTokenError):
        decode_token(mint_refresh_jwt(), expected_type="access")


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


def test_login_account_key_is_stable_and_never_contains_the_email() -> None:
    key = login_account_key("alice@example.com")
    assert key == login_account_key("alice@example.com")
    assert "alice" not in key
    assert key != hashlib.sha256(b"alice@example.com").hexdigest()


def test_case_variants_of_one_email_share_an_account_key() -> None:
    assert login_account_key("Alice@Example.com") == login_account_key("alice@example.com")


def test_different_emails_get_different_account_keys() -> None:
    assert login_account_key("alice@example.com") != login_account_key("bob@example.com")


def test_a_device_token_identifies_a_device_for_its_own_account() -> None:
    key = login_account_key("alice@example.com")
    first, second = create_login_device_token(key), create_login_device_token(key)

    assert login_device_id(first, key) is not None
    assert login_device_id(first, key) != login_device_id(second, key)


def test_a_device_token_is_worthless_for_another_account() -> None:
    token = create_login_device_token(login_account_key("attacker@example.com"))
    assert login_device_id(token, login_account_key("victim@example.com")) is None


def test_an_access_token_is_not_a_device_token() -> None:
    key = login_account_key("alice@example.com")
    assert login_device_id(create_access_token(key), key) is None


def test_a_device_token_is_not_an_access_token() -> None:
    token = create_login_device_token(login_account_key("alice@example.com"))
    with pytest.raises(jwt.InvalidTokenError):
        decode_token(token, expected_type="access")


@pytest.mark.parametrize("token", ["", "garbage", "a.b.c"])
def test_a_malformed_device_token_identifies_nothing(token: str) -> None:
    assert login_device_id(token, login_account_key("alice@example.com")) is None


def test_an_expired_device_token_identifies_nothing() -> None:
    key = login_account_key("alice@example.com")
    past = datetime.now(UTC) - timedelta(days=1)
    expired = jwt.encode(
        {"sub": key, "type": "login_device", "jti": "d", "iat": past, "exp": past},
        settings.secret_key,
        algorithm="HS256",
    )
    assert login_device_id(expired, key) is None


def test_a_forged_device_token_identifies_nothing() -> None:
    key = login_account_key("alice@example.com")
    now = datetime.now(UTC)
    forged = jwt.encode(
        {"sub": key, "type": "login_device", "jti": "d", "iat": now, "exp": now + timedelta(1)},
        "x" * 32,
        algorithm="HS256",
    )
    assert login_device_id(forged, key) is None
