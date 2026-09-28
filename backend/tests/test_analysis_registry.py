import asyncio
import uuid
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from redis.asyncio import Redis

from app.core.analysis_registry import QUEUE_KEY, AnalysisRegistry
from app.core.redis import create_redis

TTL = 600
NOW = 1_000_000.0


@pytest_asyncio.fixture
async def redis_client() -> AsyncGenerator[Redis]:
    client = create_redis()
    yield client
    await client.aclose()


@pytest.fixture
def registry(redis_client: Redis) -> AnalysisRegistry:
    return AnalysisRegistry(redis_client, ttl_seconds=TTL)


@pytest.fixture
def owner() -> str:
    return uuid.uuid4().hex


def aid() -> str:
    return uuid.uuid4().hex[:22]


async def test_the_first_analysis_takes_the_lock_with_a_ttl(
    registry: AnalysisRegistry, redis_client: Redis, owner: str
) -> None:
    first = aid()

    assert await registry.try_lock(owner, first) is None
    assert await registry.holder(owner) == first
    assert 0 < await redis_client.ttl(f"match:active:{owner}") <= TTL


async def test_a_second_analysis_learns_who_holds_the_lock(
    registry: AnalysisRegistry, owner: str
) -> None:
    first = aid()
    await registry.try_lock(owner, first)

    assert await registry.try_lock(owner, aid()) == first
    assert await registry.holder(owner) == first


async def test_locks_are_per_user(registry: AnalysisRegistry, owner: str) -> None:
    await registry.try_lock(owner, aid())

    assert await registry.try_lock(uuid.uuid4().hex, aid()) is None


async def test_concurrent_submissions_let_exactly_one_take_the_lock(
    registry: AnalysisRegistry, owner: str
) -> None:
    outcomes = await asyncio.gather(*(registry.try_lock(owner, aid()) for _ in range(10)))

    assert outcomes.count(None) == 1


async def test_replace_is_compare_and_set(registry: AnalysisRegistry, owner: str) -> None:
    first, second, third = aid(), aid(), aid()
    await registry.try_lock(owner, first)

    assert await registry.replace_lock(owner, expected=first, analysis_id=second) is True
    assert await registry.replace_lock(owner, expected=first, analysis_id=third) is False
    assert await registry.holder(owner) == second


async def test_release_only_frees_the_callers_own_lock(
    registry: AnalysisRegistry, owner: str
) -> None:
    first = aid()
    await registry.try_lock(owner, first)

    assert await registry.release_lock(owner, aid()) is False
    assert await registry.release_lock(owner, first) is True
    assert await registry.holder(owner) is None


async def test_queue_order_follows_enqueue_time(registry: AnalysisRegistry) -> None:
    a, b, c = aid(), aid(), aid()
    base = NOW + uuid.uuid4().int % 1000
    await registry.mark_queued(a, now=base)
    await registry.mark_queued(b, now=base + 1)
    await registry.mark_queued(c, now=base + 2)

    ahead = await registry.queued_before(c)

    assert ahead is not None
    assert ahead.index(a) < ahead.index(b)
    assert await registry.queued_before(aid()) is None
    await registry.forget(a, b, c)


async def test_requeueing_moves_an_analysis_to_the_back(registry: AnalysisRegistry) -> None:
    a, b = aid(), aid()
    await registry.mark_queued(a, now=NOW + 5000)
    await registry.mark_queued(b, now=NOW + 5001)

    await registry.mark_queued(a, now=NOW + 5002)

    ahead = await registry.queued_before(a)
    assert ahead is not None and b in ahead
    await registry.forget(a, b)


async def test_members_older_than_a_record_can_live_are_pruned(
    registry: AnalysisRegistry, redis_client: Redis
) -> None:
    old, new = aid(), aid()
    await redis_client.zadd(QUEUE_KEY, {old: NOW - TTL - 1})

    await registry.mark_queued(new, now=NOW)

    assert await redis_client.zscore(QUEUE_KEY, old) is None
    await registry.forget(new)


async def test_the_queue_index_expires_when_nothing_is_queued_any_more(
    registry: AnalysisRegistry, redis_client: Redis
) -> None:
    analysis = aid()
    await registry.mark_queued(analysis, now=NOW)

    assert 0 < await redis_client.ttl(QUEUE_KEY) <= TTL
    await registry.forget(analysis)

