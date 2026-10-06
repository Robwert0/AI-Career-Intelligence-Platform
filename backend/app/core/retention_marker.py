import logging
from datetime import datetime

from redis.asyncio import Redis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)

LAST_PURGE_KEY = "retention:last_purge_at"


class RetentionMarker:
    """When the inactive-account purge last succeeded, so a stopped beat process is visible."""

    def __init__(self, redis: Redis, *, key: str = LAST_PURGE_KEY) -> None:
        self._redis = redis
        self.key = key

    async def record(self, at: datetime) -> None:
        await self._redis.set(self.key, at.isoformat())

    async def last_purge_at(self) -> datetime | None:
        try:
            raw = await self._redis.get(self.key)
            if raw is None:
                return None
            return datetime.fromisoformat(raw.decode() if isinstance(raw, bytes) else raw)
        except (RedisError, ValueError) as exc:
            # A broken marker must not take the admin page down with it.
            logger.warning("retention marker unreadable error_type=%s", type(exc).__name__)
            return None
