from app.core.redis import create_redis


async def test_the_factory_reaches_a_live_redis() -> None:
    redis = create_redis()
    try:
        assert await redis.ping() is True
    finally:
        await redis.aclose()


async def test_the_client_carries_the_short_timeouts_that_bound_a_sick_redis() -> None:
    redis = create_redis()
    assert redis.connection_pool.connection_kwargs["socket_timeout"] == 0.5
    assert redis.connection_pool.connection_kwargs["socket_connect_timeout"] == 0.5
