import asyncio
import uuid
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from redis.asyncio import Redis

from app.core.rate_limiter import (
    REFUSAL_NOTICE_SECONDS,
    Policy,
    Scope,
    TokenBucketLimiter,
    ip_identity,
)
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


async def test_a_refund_returns_a_spent_token(limiter: TokenBucketLimiter, identity: str) -> None:
    spec = policy(capacity=2, refill=1 / 3600)
    for _ in range(2):
        await limiter.check(spec, identity, now=NOW)
    await limiter.refund(spec, identity, now=NOW)
    allowed = [(await limiter.check(spec, identity, now=NOW)).allowed for _ in range(2)]
    assert allowed == [True, False]


async def test_a_refund_never_lifts_a_bucket_past_capacity(
    limiter: TokenBucketLimiter, identity: str
) -> None:
    spec = policy(capacity=2, refill=1 / 3600)
    await limiter.check(spec, identity, now=NOW)
    refunds = [await limiter.refund(spec, identity, now=NOW) for _ in range(3)]
    assert refunds[-1].remaining == pytest.approx(2.0)
    allowed = [(await limiter.check(spec, identity, now=NOW)).allowed for _ in range(3)]
    assert allowed == [True, True, False]


async def test_a_refund_applies_the_refill_first(
    limiter: TokenBucketLimiter, identity: str
) -> None:
    spec = policy(capacity=3, refill=1.0)
    for _ in range(3):
        await limiter.check(spec, identity, now=NOW)
    refunded = await limiter.refund(spec, identity, now=NOW + 0.5)
    assert refunded.remaining == pytest.approx(1.5)


async def test_a_refund_on_a_missing_bucket_is_a_no_op(
    limiter: TokenBucketLimiter, redis_client: Redis, identity: str
) -> None:
    spec = policy(capacity=2)
    await limiter.refund(spec, identity, now=NOW)
    assert await redis_client.exists(f"rl:{spec.name}:{identity}") == 0
    allowed = [(await limiter.check(spec, identity, now=NOW)).allowed for _ in range(3)]
    assert allowed == [True, True, False]


async def test_a_refund_keeps_the_ttl_outliving_a_full_refill(
    limiter: TokenBucketLimiter, redis_client: Redis, identity: str
) -> None:
    spec = policy(capacity=10, refill=1 / 60)
    await limiter.check(spec, identity, now=NOW)
    await limiter.refund(spec, identity, now=NOW)
    ttl_ms = await redis_client.pttl(f"rl:{spec.name}:{identity}")
    assert ttl_ms >= (spec.capacity / spec.refill_per_second) * 1000


async def test_concurrent_takes_with_refunds_never_exceed_capacity(
    limiter: TokenBucketLimiter, identity: str
) -> None:
    spec = policy(capacity=3, refill=1 / 3600)

    async def attempt(fails: bool) -> bool:
        taken = (await limiter.check(spec, identity, now=NOW)).allowed
        if taken and fails:
            await limiter.refund(spec, identity, now=NOW)
        return taken and not fails

    kept = await asyncio.gather(*(attempt(fails=i % 2 == 0) for i in range(40)))
    assert sum(kept) <= spec.capacity


async def test_only_the_first_refusal_in_a_notice_window_is_flagged(
    limiter: TokenBucketLimiter, identity: str
) -> None:
    spec = policy(capacity=1, refill=1 / 86400)
    assert (await limiter.check(spec, identity, now=NOW)).first_refusal is False
    flags = [(await limiter.check(spec, identity, now=NOW + t)).first_refusal for t in (0, 1, 2)]
    later = await limiter.check(spec, identity, now=NOW + REFUSAL_NOTICE_SECONDS)
    assert flags == [True, False, False]
    assert later.first_refusal is True


def test_an_ipv4_client_keeps_its_address_as_the_key() -> None:
    assert ip_identity("203.0.113.7") == "203.0.113.7"


def test_an_ipv6_client_is_keyed_by_its_64() -> None:
    assert ip_identity("2001:db8:1:2:aaaa:bbbb:cccc:dddd") == "2001:db8:1:2::/64"


def test_two_addresses_in_one_64_share_a_key() -> None:
    assert ip_identity("2001:db8:1:2::1") == ip_identity("2001:db8:1:2:ffff:ffff:ffff:ffff")


def test_addresses_in_different_64s_get_different_keys() -> None:
    assert ip_identity("2001:db8:1:2::1") != ip_identity("2001:db8:1:3::1")


def test_an_ipv4_mapped_ipv6_client_shares_the_ipv4_key() -> None:
    assert ip_identity("::ffff:203.0.113.7") == ip_identity("203.0.113.7") == "203.0.113.7"


def test_a_scoped_ipv6_address_drops_its_zone() -> None:
    assert ip_identity("fe80::1%eth0") == "fe80::/64"


@pytest.mark.parametrize("host", ["testclient", "", "unix:/run/api.sock"])
def test_a_host_that_is_not_an_ip_keeps_its_own_key(host: str) -> None:
    assert ip_identity(host) == host
