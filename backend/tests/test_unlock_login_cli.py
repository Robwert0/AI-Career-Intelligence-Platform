import sys
import time
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import pytest_asyncio
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import policies
from app.core.rate_limiter import Policy, bucket_key
from app.core.redis import create_redis
from app.core.security import login_account_key
from app.models import User

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))

from unlock_login import Result, unlock_login  # noqa: E402


@pytest_asyncio.fixture
async def redis() -> AsyncIterator[Redis]:
    client = create_redis()
    yield client
    await client.aclose()


async def _locked(redis: Redis, policy: Policy, identity: str) -> str:
    key = bucket_key(policy, identity)
    await redis.hset(key, mapping={"tokens": 0, "ts": time.time()})
    await redis.expire(key, 600)
    return key


async def _add_user(session: AsyncSession) -> User:
    user = User(email=f"mira-{uuid.uuid4().hex}@test.dev", hashed_password="not-a-real-hash")
    session.add(user)
    await session.flush()
    return user


async def test_unlocking_deletes_the_account_bucket_and_nothing_else(
    db_session: AsyncSession, redis: Redis
) -> None:
    user = await _add_user(db_session)
    account = await _locked(redis, policies.LOGIN_ACCOUNT, login_account_key(user.id))
    device = await _locked(redis, policies.LOGIN_DEVICE, uuid.uuid4().hex)
    try:
        result = await unlock_login(db_session, redis, user.email.replace("i", "İ"))

        assert result is Result.UNLOCKED
        assert not await redis.exists(account)
        assert await redis.exists(device)
    finally:
        await redis.delete(account, device)


async def test_an_account_without_failures_has_nothing_to_unlock(
    db_session: AsyncSession, redis: Redis
) -> None:
    user = await _add_user(db_session)

    assert await unlock_login(db_session, redis, user.email) is Result.NOT_LOCKED


async def test_an_unknown_email_is_reported_not_found(
    db_session: AsyncSession, redis: Redis
) -> None:
    result = await unlock_login(db_session, redis, f"ghost-{uuid.uuid4().hex}@test.dev")

    assert result is Result.NOT_FOUND
