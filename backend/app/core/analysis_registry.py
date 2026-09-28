from typing import cast

from redis.asyncio import Redis

QUEUE_KEY = "match:queue"

_REPLACE_LUA = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
  redis.call('SET', KEYS[1], ARGV[2], 'EX', tonumber(ARGV[3]))
  return 1
end
return 0
"""

_RELEASE_LUA = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
  return redis.call('DEL', KEYS[1])
end
return 0
"""


def _text(value: bytes | str | None) -> str | None:
    if value is None:
        return None
    return value.decode() if isinstance(value, bytes) else value


class AnalysisRegistry:
    """The per-user active-analysis lock and the queue-position index. Written by the API only."""

    def __init__(self, redis: Redis, *, ttl_seconds: int) -> None:
        self._redis = redis
        self._ttl = ttl_seconds
        self._replace = redis.register_script(_REPLACE_LUA)
        self._release = redis.register_script(_RELEASE_LUA)

    @staticmethod
    def _lock_key(owner_id: str) -> str:
        return f"match:active:{owner_id}"

    async def try_lock(self, owner_id: str, analysis_id: str) -> str | None:
        """None when the lock was taken for analysis_id; otherwise the current holder's id."""
        key = self._lock_key(owner_id)
        while not await self._redis.set(key, analysis_id, nx=True, ex=self._ttl):
            holder = _text(await self._redis.get(key))
            # None only if the holder expired between the two calls: try to take it again.
            if holder is not None:
                return holder
        return None

    async def holder(self, owner_id: str) -> str | None:
        return _text(await self._redis.get(self._lock_key(owner_id)))

    async def replace_lock(self, owner_id: str, *, expected: str, analysis_id: str) -> bool:
        replaced = await self._replace(
            keys=[self._lock_key(owner_id)], args=[expected, analysis_id, self._ttl]
        )
        return bool(replaced)

    async def release_lock(self, owner_id: str, analysis_id: str) -> bool:
        released = await self._release(keys=[self._lock_key(owner_id)], args=[analysis_id])
        return bool(released)

    async def mark_queued(self, analysis_id: str, *, now: float) -> None:
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.zadd(QUEUE_KEY, {analysis_id: now})
            # Nothing lives longer than a record, so older members can only be leftovers.
            pipe.zremrangebyscore(QUEUE_KEY, "-inf", now - self._ttl)
            await pipe.execute()

    async def forget(self, *analysis_ids: str) -> None:
        if analysis_ids:
            await self._redis.zrem(QUEUE_KEY, *analysis_ids)

    async def queued_before(self, analysis_id: str) -> list[str] | None:
        rank = cast(int | None, await self._redis.zrank(QUEUE_KEY, analysis_id))
        if rank is None:
            return None
        if rank == 0:
            return []
        members = cast(list[bytes], await self._redis.zrange(QUEUE_KEY, 0, rank - 1))
        return [member.decode() for member in members]
