import hashlib
import hmac
import string
import uuid
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
    unregistered_login_key,
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


def _device_signing_key() -> bytes:
    return hmac.new(settings.secret_key.encode(), b"jwt-login-device", hashlib.sha256).digest()


def _device_claims(key: str, issued: datetime) -> dict[str, object]:
    return {
        "sub": key,
        "type": "login_device",
        "aud": "login_device",
        "jti": "d",
        "iat": issued,
        "exp": issued + timedelta(days=1),
    }


def test_an_account_key_is_stable_and_never_contains_the_id() -> None:
    user_id = uuid.uuid4()
    key = login_account_key(user_id)
    assert key == login_account_key(user_id)
    assert str(user_id) not in key
    assert key != login_account_key(uuid.uuid4())


def test_an_unregistered_key_never_contains_the_email() -> None:
    key = unregistered_login_key("alice@example.com")
    assert key == unregistered_login_key("alice@example.com")
    assert "alice" not in key
    assert key != hashlib.sha256(b"alice@example.com").hexdigest()
    assert key != unregistered_login_key("bob@example.com")


def test_an_account_key_and_an_unregistered_key_never_collide() -> None:
    user_id = uuid.uuid4()
    assert login_account_key(user_id) != unregistered_login_key(str(user_id))


def test_account_keys_use_a_subkey_not_the_raw_secret() -> None:
    user_id = uuid.uuid4()
    raw = hmac.new(
        settings.secret_key.encode(), b"user:" + str(user_id).encode(), hashlib.sha256
    ).hexdigest()
    assert login_account_key(user_id) != raw


def test_a_device_token_identifies_a_device_for_its_own_account() -> None:
    key = login_account_key(uuid.uuid4())
    first, second = create_login_device_token(key), create_login_device_token(key)

    assert login_device_id(first, key) is not None
    assert login_device_id(first, key) != login_device_id(second, key)


def test_a_device_token_is_worthless_for_another_account() -> None:
    token = create_login_device_token(login_account_key(uuid.uuid4()))
    assert login_device_id(token, login_account_key(uuid.uuid4())) is None


def test_an_access_token_is_not_a_device_token() -> None:
    key = login_account_key(uuid.uuid4())
    assert login_device_id(create_access_token(key), key) is None


def test_a_device_token_is_not_an_access_token() -> None:
    token = create_login_device_token(login_account_key(uuid.uuid4()))
    with pytest.raises(jwt.InvalidTokenError):
        decode_token(token, expected_type="access")


@pytest.mark.parametrize("token", ["", "garbage", "a.b.c"])
def test_a_malformed_device_token_identifies_nothing(token: str) -> None:
    assert login_device_id(token, login_account_key(uuid.uuid4())) is None


def test_an_expired_device_token_identifies_nothing() -> None:
    key = login_account_key(uuid.uuid4())
    claims = _device_claims(key, datetime.now(UTC) - timedelta(days=2))
    expired = jwt.encode(claims, _device_signing_key(), algorithm="HS256")
    assert login_device_id(expired, key) is None


def test_a_forged_device_token_identifies_nothing() -> None:
    key = login_account_key(uuid.uuid4())
    forged = jwt.encode(_device_claims(key, datetime.now(UTC)), "x" * 32, algorithm="HS256")
    assert login_device_id(forged, key) is None


def test_a_device_token_signed_with_the_raw_secret_identifies_nothing() -> None:
    key = login_account_key(uuid.uuid4())
    claims = _device_claims(key, datetime.now(UTC))
    assert login_device_id(jwt.encode(claims, settings.secret_key, algorithm="HS256"), key) is None


def test_a_device_token_without_its_audience_identifies_nothing() -> None:
    key = login_account_key(uuid.uuid4())
    claims = _device_claims(key, datetime.now(UTC))
    del claims["aud"]
    assert (
        login_device_id(jwt.encode(claims, _device_signing_key(), algorithm="HS256"), key) is None
    )


def test_a_correctly_signed_device_token_identifies_its_device() -> None:
    key = login_account_key(uuid.uuid4())
    token = jwt.encode(_device_claims(key, datetime.now(UTC)), _device_signing_key(), "HS256")
    assert login_device_id(token, key) == "d"
