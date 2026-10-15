import logging
from types import SimpleNamespace
from typing import Any, cast

import pytest
from fastapi import Request

from app.ai.ollama import OllamaGenerator
from app.ai.openai import OpenAIGenerator
from app.ai.spend_guard import BudgetedGenerator
from app.core.config import settings
from app.core.spend_ledger import RedisSpendLedger, SpendPool
from app.deps import get_generator
from app.main import app, lifespan


async def test_the_lifespan_opens_a_usable_limiter_and_closes_the_pool() -> None:
    async with lifespan(app):
        assert await app.state.redis.ping() is True
        assert app.state.limiter is not None


async def test_the_lifespan_owns_one_guarded_generator() -> None:
    async with lifespan(app):
        provider = OpenAIGenerator if settings.generation_provider == "openai" else OllamaGenerator
        expected = BudgetedGenerator if settings.llm_spend_guard_enabled else provider
        assert isinstance(app.state.generator, expected)


async def test_get_generator_hands_out_the_shared_instance() -> None:
    async with lifespan(app):
        request = SimpleNamespace(app=app)

        assert get_generator(cast(Request, request)) is app.state.generator


def _provider(generator: Any) -> Any:
    return generator._inner if isinstance(generator, BudgetedGenerator) else generator


async def test_the_generator_uses_the_chat_timeout_not_the_script_timeout() -> None:
    async with lifespan(app):
        timeout = _provider(app.state.generator)._client.timeout

        assert timeout.read == float(settings.chat_timeout_seconds)
        assert timeout.connect == float(settings.generation_connect_timeout_seconds)


async def test_the_generator_client_is_closed_on_shutdown() -> None:
    async with lifespan(app):
        generator = _provider(app.state.generator)

    assert generator._client.is_closed


async def test_the_lifespan_owns_a_celery_task_queue() -> None:
    from app.workers.queue import CeleryTaskQueue

    async with lifespan(app):
        assert isinstance(app.state.task_queue, CeleryTaskQueue)


async def test_the_lifespan_refuses_to_start_without_a_cv_document_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "cv_document_id", None)

    with pytest.raises(RuntimeError, match="CV_DOCUMENT_ID"):
        async with lifespan(app):
            pass


async def test_the_lifespan_generator_draws_on_the_chat_pool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "llm_spend_guard_enabled", True)
    async with lifespan(app):
        ledger = app.state.generator._ledger
        assert isinstance(ledger, RedisSpendLedger)
        assert ledger._pool is SpendPool.CHAT


async def test_the_lifespan_logs_the_chat_budget_once(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(settings, "llm_spend_guard_enabled", True)
    with caplog.at_level(logging.INFO, logger="app.ai.spend_guard"):
        async with lifespan(app):
            pass
    assert caplog.text.count("llm spend guard pool=chat") == 1
