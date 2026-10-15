"""Lift a sign-in lockout: delete one account's LOGIN_ACCOUNT failure bucket, and only that.

    cd backend && python scripts/unlock_login.py visitor@example.com

Needs DATABASE_URL, REDIS_URL and the production SECRET_KEY: the bucket is keyed by an HMAC of
the account id. Per-device, per-IP and per-/48 buckets are left to refill on their own.
"""

import argparse
import asyncio
import enum
import logging
import sys

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import policies
from app.core.db import SessionLocal
from app.core.log_config import configure_logging
from app.core.rate_limiter import bucket_key
from app.core.redis import create_redis
from app.repositories import RefreshTokenRepository, UserRepository
from app.schemas.auth import normalize_email
from app.services import AuthService

logger = logging.getLogger("unlock_login")


class Result(enum.Enum):
    UNLOCKED = "unlocked"
    NOT_LOCKED = "not_locked"
    NOT_FOUND = "not_found"


EXIT_CODES = {Result.UNLOCKED: 0, Result.NOT_LOCKED: 0, Result.NOT_FOUND: 1}
EXIT_INVALID_EMAIL = 2
EXIT_UNEXPECTED = 4


async def unlock_login(session: AsyncSession, redis: Redis, email: str) -> Result:
    # Resolved the way /auth/login resolves it, so any spelling of the email reaches its bucket.
    auth = AuthService(UserRepository(session), RefreshTokenRepository(session))
    account = await auth.resolve_login(email)
    if account.user is None:
        return Result.NOT_FOUND
    deleted = await redis.delete(bucket_key(policies.LOGIN_ACCOUNT, account.key))
    return Result.UNLOCKED if deleted else Result.NOT_LOCKED


async def _run(email: str) -> Result:
    redis = create_redis()
    try:
        async with SessionLocal() as session:
            return await unlock_login(session, redis, email)
    finally:
        await redis.aclose()


def _report(result: Result, email: str) -> None:
    if result is Result.UNLOCKED:
        logger.info("sign-in lockout lifted policy=%s", policies.LOGIN_ACCOUNT.name)
        print(f"unlocked sign-in for {email}")
    elif result is Result.NOT_LOCKED:
        print(f"{email} had no failed sign-ins on record — nothing to unlock")
    else:
        print(f"no user with email {email}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Lift the account-wide sign-in lockout for one account.",
        epilog=(
            "Run from backend/ with DATABASE_URL, REDIS_URL and SECRET_KEY set. "
            "Exit codes: 0 unlocked (or nothing to unlock), 1 no such user, "
            "2 invalid email, 4 unexpected error."
        ),
    )
    parser.add_argument("email")
    args = parser.parse_args()

    try:
        email = normalize_email(args.email)
    except ValueError as exc:
        print(f"not a valid email address: {exc}", file=sys.stderr)
        return EXIT_INVALID_EMAIL

    configure_logging("INFO")
    try:
        result = asyncio.run(_run(email))
        _report(result, email)
    except Exception as exc:
        # The message can carry bound values or account data; the type is enough to debug.
        print(f"unexpected error: {type(exc).__name__}", file=sys.stderr)
        return EXIT_UNEXPECTED
    return EXIT_CODES[result]


if __name__ == "__main__":
    sys.exit(main())
