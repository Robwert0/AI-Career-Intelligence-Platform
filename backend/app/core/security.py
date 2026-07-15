from datetime import UTC, datetime, timedelta
from typing import Any

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
    claims = {
        "sub": subject,
        "type": "access",
        "exp": datetime.now(UTC) + timedelta(minutes=settings.access_token_expire_minutes),
    }
    return jwt.encode(claims, settings.secret_key, algorithm="HS256")


def create_refresh_token(subject: str) -> str:
    claims = {
        "sub": subject,
        "type": "refresh",
        "exp": datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days),
    }
    return jwt.encode(claims, settings.secret_key, algorithm="HS256")


def decode_token(token: str) -> dict[str, Any] -> str:
    return jwt.decode(token, settings.secret_key, algorithms=["HS256"])
