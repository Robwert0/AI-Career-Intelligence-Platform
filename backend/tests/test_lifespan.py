from app.main import app, lifespan


async def test_the_lifespan_opens_a_usable_limiter_and_closes_the_pool() -> None:
    async with lifespan(app):
        assert await app.state.redis.ping() is True
        assert app.state.limiter is not None
