import asyncio
import uuid
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from redis.asyncio import Redis

from app.core.rate_limiter import Policy, Scope, TokenBucketLimiter
from app.core.redis import create_redis

NOW = 1_000_000.0


@pytest_asyncio.fixture
async def redis_client() -> AsyncGenerator[Redis]:
    client = create_redis()
    yield client
    await client.aclose()


@pytest.fixture
def limiter(redis_client: Redis) -> TokenBucketLimiter:
    return TokenBucketLimiter(redis_client)


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


async def test_fractional_tokens_survive_the_round_trip(
    limiter: TokenBucketLimiter, identity: str
) -> None:
    spec = policy(capacity=5, refill=1.0)
    await limiter.check(spec, identity, now=NOW)
    decision = await limiter.check(spec, identity, now=NOW + 0.5)
    # Redis truncates a raw Lua float to an integer, which would make this 3.0.
    assert decision.remaining == pytest.approx(3.5)


async def test_tokens_never_exceed_capacity_however_long_the_bucket_idles(
    limiter: TokenBucketLimiter, identity: str
) -> None:
    spec = policy(capacity=3, refill=1.0)
    await limiter.check(spec, identity, now=NOW)
    later = NOW + 10_000_000
    allowed = [(await limiter.check(spec, identity, now=later)).allowed for _ in range(4)]
    assert allowed == [True, True, True, False]


async def test_a_backwards_clock_never_mints_tokens(
    limiter: TokenBucketLimiter, identity: str
) -> None:
    spec = policy(capacity=2, refill=1.0)
    for _ in range(2):
        await limiter.check(spec, identity, now=NOW)
    decision = await limiter.check(spec, identity, now=NOW - 3600)
    assert decision.allowed is False
    assert decision.remaining >= 0


async def test_a_denied_request_does_not_consume_a_token(
    limiter: TokenBucketLimiter, identity: str
) -> None:
    spec = policy(capacity=1, refill=1.0)
    await limiter.check(spec, identity, now=NOW)
    for _ in range(20):
        assert (await limiter.check(spec, identity, now=NOW)).allowed is False
    allowed = [(await limiter.check(spec, identity, now=NOW + 1.0)).allowed for _ in range(2)]
    assert allowed == [True, False]


async def test_the_ttl_outlives_a_full_refill(
    limiter: TokenBucketLimiter, redis_client: Redis, identity: str
) -> None:
    spec = policy(capacity=10, refill=1 / 60)
    await limiter.check(spec, identity, now=NOW)
    ttl_ms = await redis_client.pttl(f"rl:{spec.name}:{identity}")
    assert ttl_ms >= (spec.capacity / spec.refill_per_second) * 1000


async def test_two_identities_do_not_share_a_bucket(limiter: TokenBucketLimiter) -> None:
    spec = policy(capacity=1, refill=1.0)
    first, second = uuid.uuid4().hex, uuid.uuid4().hex
    assert (await limiter.check(spec, first, now=NOW)).allowed is True
    assert (await limiter.check(spec, first, now=NOW)).allowed is False
    assert (await limiter.check(spec, second, now=NOW)).allowed is True


async def test_two_policies_on_one_identity_do_not_share_a_bucket(
    limiter: TokenBucketLimiter, identity: str
) -> None:
    first = Policy("a", capacity=1, refill_per_second=1.0, scope=Scope.IP)
    second = Policy("b", capacity=1, refill_per_second=1.0, scope=Scope.IP)
    assert (await limiter.check(first, identity, now=NOW)).allowed is True
    assert (await limiter.check(first, identity, now=NOW)).allowed is False
    assert (await limiter.check(second, identity, now=NOW)).allowed is True


async def test_fifty_concurrent_requests_on_capacity_ten_allow_exactly_ten(
    limiter: TokenBucketLimiter, identity: str
) -> None:
    spec = policy(capacity=10, refill=1.0)
    decisions = await asyncio.gather(*(limiter.check(spec, identity, now=NOW) for _ in range(50)))
    assert sum(d.allowed for d in decisions) == 10
