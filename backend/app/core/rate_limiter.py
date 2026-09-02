from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from redis.asyncio import Redis

Scope = StrEnum("Scope", ["IP", "USER"])


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


class Limiter(Protocol):
    async def check(self, policy: Policy, identity: str, *, now: float) -> Decision: ...


TOKEN_BUCKET_LUA = """
local key      = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill   = tonumber(ARGV[2])
local now      = tonumber(ARGV[3])

local bucket = redis.call('HMGET', key, 'tokens', 'ts')
local tokens = tonumber(bucket[1])
local ts     = tonumber(bucket[2])

if tokens == nil then
  tokens = capacity
  ts = now
end

-- A backwards clock must never mint tokens: clamp elapsed at zero.
local elapsed = math.max(0, now - ts)
tokens = math.min(capacity, tokens + elapsed * refill)

local allowed, retry = 0, 0.0
if tokens >= 1 then
  tokens  = tokens - 1
  allowed = 1
else
  retry = (1 - tokens) / refill
end

redis.call('HSET', key, 'tokens', tokens, 'ts', now)
-- Must outlive a full refill: expiring early resets the bucket to capacity, i.e. free budget.
redis.call('PEXPIRE', key, math.ceil((capacity / refill) * 1000) + 1000)

-- Floats must leave as strings: Redis truncates Lua numbers to integers.
return { allowed, tostring(tokens), tostring(retry) }
"""


class TokenBucketLimiter:
    def __init__(self, redis: Redis) -> None:
        self._script = redis.register_script(TOKEN_BUCKET_LUA)

    async def check(self, policy: Policy, identity: str, *, now: float) -> Decision:
        key = f"rl:{policy.name}:{identity}"
        allowed, remaining, retry_after = await self._script(
            keys=[key], args=[policy.capacity, policy.refill_per_second, now]
        )
        return Decision(
            allowed=bool(allowed),
            remaining=float(remaining),
            retry_after_seconds=float(retry_after),
        )
