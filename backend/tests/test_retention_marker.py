import logging
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from redis.asyncio import Redis

from app.core.redis import create_redis
from app.core.retention_marker import LAST_PURGE_KEY, RetentionMarker

AT = datetime(2026, 10, 5, 3, 0, 1, tzinfo=UTC)


@pytest_asyncio.fixture
async def redis_client() -> AsyncGenerator[Redis]:
    client = create_redis()
    yield client
    await client.aclose()


@pytest_asyncio.fixture
async def marker(redis_client: Redis) -> AsyncGenerator[RetentionMarker]:
    key = f"test:{uuid.uuid4()}"
    yield RetentionMarker(redis_client, key=key)
    await redis_client.delete(key)


def test_the_production_key_is_the_documented_one() -> None:
    assert LAST_PURGE_KEY == "retention:last_purge_at"


async def test_a_recorded_purge_reads_back_as_the_same_utc_time(
    marker: RetentionMarker, redis_client: Redis
) -> None:
    await marker.record(AT)

    assert await marker.last_purge_at() == AT
    assert await redis_client.ttl(marker.key) == -1


async def test_no_purge_yet_reads_as_none(marker: RetentionMarker) -> None:
    assert await marker.last_purge_at() is None


async def test_an_unreachable_redis_reads_as_none_and_logs_only_the_error_type(
    caplog: pytest.LogCaptureFixture,
) -> None:
    dead = Redis.from_url("redis://127.0.0.1:1/0", socket_connect_timeout=0.5)
    caplog.set_level(logging.WARNING, logger="app.core.retention_marker")
    try:
        assert await RetentionMarker(dead).last_purge_at() is None
    finally:
        await dead.aclose()

    assert [record.getMessage() for record in caplog.records] == [
        "retention marker unreadable error_type=ConnectionError"
    ]


async def test_a_corrupt_value_reads_as_none_and_logs_only_the_error_type(
    marker: RetentionMarker, redis_client: Redis, caplog: pytest.LogCaptureFixture
) -> None:
    await redis_client.set(marker.key, "not-a-timestamp")
    caplog.set_level(logging.WARNING, logger="app.core.retention_marker")

    assert await marker.last_purge_at() is None
    assert [record.getMessage() for record in caplog.records] == [
        "retention marker unreadable error_type=ValueError"
    ]
