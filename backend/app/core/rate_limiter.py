from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, Protocol

from redis.asyncio import Redis

Scope = StrEnum("Scope", ["IP", "USER", "GLOBAL"])


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
    # Set on the first peek refusal per REFUSAL_NOTICE_SECONDS, so a flood logs once, not per hit.
    first_refusal: bool = False


class Limiter(Protocol):
    async def check(self, policy: Policy, identity: str, *, now: float) -> Decision: ...

    async def peek(self, policy: Policy, identity: str, *, now: float) -> Decision: ...

    async def charge(self, policy: Policy, identity: str, *, now: float) -> Decision: ...


REFUSAL_NOTICE_SECONDS = 60

# Modes: 'take' spends a token only if one exists; 'peek' never spends; 'charge' always spends,
# so the bucket may go negative and later peeks refuse until the debt refills.
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
  tokens = capacity
  ts = now
end

-- A backwards clock must never mint tokens: clamp elapsed at zero.
local elapsed = math.max(0, now - ts)
tokens = math.min(capacity, tokens + elapsed * refill)

if mode == 'peek' then
  if tokens >= 1 then
    return { 1, tostring(tokens), '0', 0 }
  end
  -- A refusal means the bucket was spent, so the key exists and HSET keeps its TTL.
  local first = 0
  if now >= (tonumber(bucket[3]) or 0) then
    redis.call('HSET', key, 'noticed_until', now + notice)
    first = 1
  end
  return { 0, tostring(tokens), tostring((1 - tokens) / refill), first }
end

local allowed, retry = 0, 0.0
if mode == 'charge' or tokens >= 1 then
  tokens  = tokens - 1
  allowed = 1
else
  retry = (1 - tokens) / refill
end

redis.call('HSET', key, 'tokens', tokens, 'ts', now)
-- Must outlive a full refill: expiring early resets the bucket to capacity, i.e. free budget.
local deficit = capacity - math.min(tokens, 0)
redis.call('PEXPIRE', key, math.ceil((deficit / refill) * 1000) + 1000)

-- Floats must leave as strings: Redis truncates Lua numbers to integers.
return { allowed, tostring(tokens), tostring(retry), 0 }
"""

_Mode = Literal["take", "peek", "charge"]


class TokenBucketLimiter:
    def __init__(self, redis: Redis) -> None:
        self._script = redis.register_script(TOKEN_BUCKET_LUA)

    async def check(self, policy: Policy, identity: str, *, now: float) -> Decision:
        return await self._run(policy, identity, now, "take")

    async def peek(self, policy: Policy, identity: str, *, now: float) -> Decision:
        return await self._run(policy, identity, now, "peek")

    async def charge(self, policy: Policy, identity: str, *, now: float) -> Decision:
        return await self._run(policy, identity, now, "charge")

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
