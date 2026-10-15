import ipaddress
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, Protocol

from redis.asyncio import Redis

# ACCOUNT policies key on a credential-derived id from the body, so a route charges them itself.
Scope = StrEnum("Scope", ["IP", "IP_PREFIX", "USER", "ACCOUNT", "GLOBAL"])


@dataclass(frozen=True, slots=True)
class Policy:
    name: str
    capacity: int
    refill_per_second: float
    scope: Scope

    def __post_init__(self) -> None:
        if self.capacity < 1:
            raise ValueError("capacity must be at least 1; a bucket of 0 denies everything")
        if self.refill_per_second <= 0:
            raise ValueError("refill_per_second must be positive; 0 divides by zero in the script")


@dataclass(frozen=True, slots=True)
class Decision:
    allowed: bool
    remaining: float
    retry_after_seconds: float
    # Set on the first refusal per REFUSAL_NOTICE_SECONDS, so a flood logs once, not per hit.
    first_refusal: bool = False


class Limiter(Protocol):
    async def check(self, policy: Policy, identity: str, *, now: float) -> Decision: ...

    # Only the reserving context managers in deps may call this: a refund without its matching
    # take mints a token.
    async def refund(self, policy: Policy, identity: str, *, now: float) -> Decision: ...


def _ipv6_network_identity(host: str, prefix_length: int) -> str:
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return host
    if not isinstance(address, ipaddress.IPv6Address):
        return host
    if address.ipv4_mapped is not None:
        return str(address.ipv4_mapped)
    return str(ipaddress.IPv6Network((address, prefix_length), strict=False))


def ip_identity(host: str) -> str:
    # One IPv6 subscriber holds at least a /64; keying per address would hand them 2**64 buckets.
    return _ipv6_network_identity(host, 64)


def ip_prefix_identity(host: str) -> str:
    # A /48 is a free tunnelbroker allocation, i.e. 65,536 /64 buckets for one person.
    return _ipv6_network_identity(host, 48)


REFUSAL_NOTICE_SECONDS = 60

# Modes: 'take' spends a token only if one exists; 'refund' returns one, capped at capacity, and
# is a no-op on a missing key because a missing bucket is already full.
TOKEN_BUCKET_LUA = """
local key      = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill   = tonumber(ARGV[2])
local now      = tonumber(ARGV[3])
local mode     = ARGV[4]
local notice   = tonumber(ARGV[5])

local bucket = redis.call('HMGET', key, 'tokens', 'ts', 'noticed_until')
local tokens = tonumber(bucket[1])
local ts     = tonumber(bucket[2])

if tokens == nil then
  if mode == 'refund' then
    return { 1, tostring(capacity), '0', 0 }
  end
  tokens = capacity
  ts = now
end

-- A backwards clock must never mint tokens: clamp elapsed at zero.
local elapsed = math.max(0, now - ts)
tokens = math.min(capacity, tokens + elapsed * refill)

local allowed, retry, first = 1, 0.0, 0
if mode == 'refund' then
  tokens = math.min(capacity, tokens + 1)
elseif tokens >= 1 then
  tokens = tokens - 1
else
  allowed = 0
  retry = (1 - tokens) / refill
  if now >= (tonumber(bucket[3]) or 0) then
    redis.call('HSET', key, 'noticed_until', now + notice)
    first = 1
  end
end

redis.call('HSET', key, 'tokens', tokens, 'ts', now)
-- Must outlive a full refill: expiring early resets the bucket to capacity, i.e. free budget.
redis.call('PEXPIRE', key, math.ceil((capacity / refill) * 1000) + 1000)

-- Floats must leave as strings: Redis truncates Lua numbers to integers.
return { allowed, tostring(tokens), tostring(retry), first }
"""

_Mode = Literal["take", "refund"]


class TokenBucketLimiter:
    def __init__(self, redis: Redis) -> None:
        self._script = redis.register_script(TOKEN_BUCKET_LUA)

    async def check(self, policy: Policy, identity: str, *, now: float) -> Decision:
        return await self._run(policy, identity, now, "take")

    async def refund(self, policy: Policy, identity: str, *, now: float) -> Decision:
        return await self._run(policy, identity, now, "refund")

    async def _run(self, policy: Policy, identity: str, now: float, mode: _Mode) -> Decision:
        key = f"rl:{policy.name}:{identity}"
        allowed, remaining, retry_after, first_refusal = await self._script(
            keys=[key],
            args=[policy.capacity, policy.refill_per_second, now, mode, REFUSAL_NOTICE_SECONDS],
        )
        return Decision(
            allowed=bool(allowed),
            remaining=float(remaining),
            retry_after_seconds=float(retry_after),
            first_refusal=bool(first_refusal),
        )
