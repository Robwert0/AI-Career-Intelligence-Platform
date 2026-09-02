import uuid
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio

from app.core.rate_limiter import Policy, Scope, TokenBucketLimiter
from app.core.redis import create_redis

NOW = 1_000_000.0


@pytest_asyncio.fixture
async def limiter() -> AsyncGenerator[TokenBucketLimiter]:
    client = create_redis()
    yield TokenBucketLimiter(client)
    await client.aclose()


@pytest.fixture
def identity() -> str:
    return uuid.uuid4().hex


def policy(capacity: int = 5, refill: float = 1.0) -> Policy:
    return Policy("test", capacity=capacity, refill_per_second=refill, scope=Scope.IP)


async def test_a_fresh_bucket_allows_exactly_capacity_then_denies(
    limiter: TokenBucketLimiter, identity: str
) -> None:
    allowed = [
        (await limiter.check(policy(capacity=3), identity, now=NOW)).allowed for _ in range(4)
    ]
    assert allowed == [True, True, True, False]


async def test_a_denial_reports_how_long_until_one_token_exists(
    limiter: TokenBucketLimiter, identity: str
) -> None:
    spec = policy(capacity=1, refill=0.5)
    await limiter.check(spec, identity, now=NOW)
    denied = await limiter.check(spec, identity, now=NOW)
    assert denied.allowed is False
    assert denied.retry_after_seconds == pytest.approx(2.0)


async def test_advancing_the_clock_one_refill_period_grants_exactly_one_more(
    limiter: TokenBucketLimiter, identity: str
) -> None:
    spec = policy(capacity=2, refill=1.0)
    for _ in range(2):
        await limiter.check(spec, identity, now=NOW)
    assert (await limiter.check(spec, identity, now=NOW + 1.0)).allowed is True
    assert (await limiter.check(spec, identity, now=NOW + 1.0)).allowed is False


async def test_the_result_reports_what_is_left(limiter: TokenBucketLimiter, identity: str) -> None:
    decision = await limiter.check(policy(capacity=5), identity, now=NOW)
    assert decision.remaining == pytest.approx(4.0)
