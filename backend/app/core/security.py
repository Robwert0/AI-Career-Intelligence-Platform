import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import bcrypt
import jwt

from app.core.config import settings


def hash_password(password: str) -> str:
    if len(password.encode("utf-8")) > 72:
        raise ValueError("Password too long")
    return (bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


def create_access_token(subject: str) -> str:
    now = datetime.now(UTC)
    claims = {
        "sub": subject,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
    }
    return jwt.encode(claims, settings.secret_key, algorithm="HS256")


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(32)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def decode_token(token: str, expected_type: str) -> dict[str, Any]:
    payload = jwt.decode(
        token,
        settings.secret_key,
        algorithms=["HS256"],
        options={"require": ["sub", "type", "iat", "exp"]},
    )
    if payload["type"] != expected_type:
        raise jwt.InvalidTokenError("Wrong token type")
    return payload


LOGIN_DEVICE_COOKIE = "__Host-login_device"
_LOGIN_DEVICE = "login_device"


def _subkey(purpose: bytes) -> bytes:
    # One secret, one subkey per use: a value minted for one purpose can never verify as another.
    return hmac.new(settings.secret_key.encode("utf-8"), purpose, hashlib.sha256).digest()


def _login_key(message: bytes) -> str:
    # Keyed, so neither Redis nor a leaked dump maps a bucket back to an account or an email.
    return hmac.new(_subkey(b"login-account-key"), message, hashlib.sha256).hexdigest()


def login_account_key(user_id: UUID) -> str:
    return _login_key(b"user:" + str(user_id).encode("ascii"))


def unregistered_login_key(canonical_email: str) -> str:
    return _login_key(b"email:" + canonical_email.encode("utf-8"))


def create_login_device_token(account_key: str) -> str:
    now = datetime.now(UTC)
    claims = {
        "sub": account_key,
        "type": _LOGIN_DEVICE,
        "aud": _LOGIN_DEVICE,
        "jti": secrets.token_urlsafe(16),
        "iat": now,
        "exp": now + timedelta(days=settings.login_device_expire_days),
    }
    return jwt.encode(claims, _subkey(b"jwt-login-device"), algorithm="HS256")


def login_device_id(token: str, account_key: str) -> str | None:
    try:
        payload = jwt.decode(
            token,
            _subkey(b"jwt-login-device"),
            algorithms=["HS256"],
            audience=_LOGIN_DEVICE,
            options={"require": ["sub", "type", "aud", "jti", "iat", "exp"]},
        )
    except jwt.InvalidTokenError:
        return None
    device_id, subject = payload["jti"], payload["sub"]
    if payload["type"] != _LOGIN_DEVICE:
        return None
    if not isinstance(device_id, str) or not isinstance(subject, str):
        return None
    return device_id if hmac.compare_digest(subject, account_key) else None
