from types import SimpleNamespace
from typing import cast

from fastapi import Request

from app.ai.ollama import OllamaGenerator
from app.core.config import settings
from app.deps import get_generator
from app.main import app, lifespan


async def test_the_lifespan_opens_a_usable_limiter_and_closes_the_pool() -> None:
    async with lifespan(app):
        assert await app.state.redis.ping() is True
        assert app.state.limiter is not None


async def test_the_lifespan_owns_one_generator() -> None:
    async with lifespan(app):
        assert isinstance(app.state.generator, OllamaGenerator)


async def test_get_generator_hands_out_the_shared_instance() -> None:
    async with lifespan(app):
        request = SimpleNamespace(app=app)

        assert get_generator(cast(Request, request)) is app.state.generator


async def test_the_generator_uses_the_chat_timeout_not_the_script_timeout() -> None:
    async with lifespan(app):
        timeout = app.state.generator._client.timeout

        assert timeout.read == float(settings.chat_timeout_seconds)
        assert timeout.connect == float(settings.generation_connect_timeout_seconds)


async def test_the_generator_client_is_closed_on_shutdown() -> None:
    async with lifespan(app):
        generator = app.state.generator

    assert generator._client.is_closed
