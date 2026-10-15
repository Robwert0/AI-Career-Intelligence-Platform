import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from redis.asyncio import Redis

logger = logging.getLogger(__name__)

WARN_FRACTION = 0.8
# Outlives the UTC day it counts, so a late settle still finds its key.
DAY_KEY_TTL_SECONDS = 2 * 24 * 3600

RESERVE_LUA = """
local spent_key, warned_key, exhausted_key = KEYS[1], KEYS[2], KEYS[3]
local amount  = tonumber(ARGV[1])
local budget  = tonumber(ARGV[2])
local warn_at = tonumber(ARGV[3])
local ttl     = tonumber(ARGV[4])

local spent = tonumber(redis.call('GET', spent_key) or '0')
if spent + amount > budget then
  local first = redis.call('SET', exhausted_key, '1', 'NX', 'EX', ttl)
  return { 0, spent, first and 1 or 0 }
end

local total = redis.call('INCRBY', spent_key, amount)
redis.call('EXPIRE', spent_key, ttl)
local crossed = 0
if total >= warn_at and redis.call('SET', warned_key, '1', 'NX', 'EX', ttl) then
  crossed = 1
end
return { 1, total, crossed }
"""

# A settle after the key expired must not recreate it holding a negative balance.
SETTLE_LUA = """
if redis.call('EXISTS', KEYS[1]) == 1 then
  return redis.call('INCRBY', KEYS[1], ARGV[1])
end
return 0
"""


@dataclass(frozen=True, slots=True)
class Reservation:
    key: str
    micro_usd: int


class RedisSpendLedger:
    def __init__(
        self,
        redis: Redis,
        *,
        daily_budget_micro_usd: int,
        key_prefix: str = "llm_spend",
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._redis = redis
        self._reserve = redis.register_script(RESERVE_LUA)
        self._settle = redis.register_script(SETTLE_LUA)
        self._budget = daily_budget_micro_usd
        self._prefix = key_prefix
        self._clock = clock

    def _keys(self) -> tuple[str, str, str]:
        # One hash tag per day keeps all three keys in one cluster slot, as Lua requires.
        tag = f"{{{self._prefix}:{self._clock().date().isoformat()}}}"
        return f"{tag}:spent", f"{tag}:warned", f"{tag}:exhausted"

    async def reserve(self, micro_usd: int) -> Reservation | None:
        spent_key, warned_key, exhausted_key = self._keys()
        allowed, total, flagged = await self._reserve(
            keys=[spent_key, warned_key, exhausted_key],
            args=[micro_usd, self._budget, int(self._budget * WARN_FRACTION), DAY_KEY_TTL_SECONDS],
        )
        if not allowed:
            if flagged:
                logger.warning(
                    "llm daily budget exhausted spent_micro_usd=%d budget_micro_usd=%d",
                    int(total),
                    self._budget,
                )
            return None
        if flagged:
            logger.warning(
                "llm daily spend passed %d%% of budget spent_micro_usd=%d budget_micro_usd=%d",
                int(WARN_FRACTION * 100),
                int(total),
                self._budget,
            )
        return Reservation(key=spent_key, micro_usd=micro_usd)

    async def settle(self, reservation: Reservation, actual_micro_usd: int) -> None:
        await self._settle(keys=[reservation.key], args=[actual_micro_usd - reservation.micro_usd])

    async def spent_today(self) -> int:
        raw = await self._redis.get(self._keys()[0])
        return int(raw or 0)
