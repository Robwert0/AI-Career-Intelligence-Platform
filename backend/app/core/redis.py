import redis.asyncio as redis

from app.core.config import settings


def create_redis() -> redis.Redis:
    return redis.Redis.from_url(
        settings.redis_url,
        socket_timeout=0.5,
        socket_connect_timeout=0.5,
    )
