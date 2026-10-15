import asyncio
import json
import logging
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import pytest
import pytest_asyncio
from fakes import FakeGenerator
from redis.asyncio import Redis
from redis.exceptions import ConnectionError as RedisConnectionError

from app.ai.generation import (
    ContextOverflowError,
    GenerationRequestError,
    GenerationResult,
    GeneratorUnavailableError,
    Message,
    Role,
    SamplingSettings,
)
from app.ai.json_schema import strict_schema
from app.ai.match.structured import ExtractionError, _generate
from app.ai.spend_guard import (
    BudgetedGenerator,
    SpendBudgetExceededError,
    cost_micro_usd,
    daily_budget_usd,
    guarded,
    log_spend_guard_config,
    prompt_token_ceiling,
)
from app.core.config import settings
from app.core.redis import create_redis
from app.core.spend_ledger import RedisSpendLedger, Reservation, SpendPool, seconds_until_reset

DAY = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)
SECRET = "candidate phone 555-0100"
MESSAGES = [Message(Role.SYSTEM, "You answer questions."), Message(Role.USER, SECRET)]
SAMPLING = SamplingSettings(max_output_tokens=100)


@pytest_asyncio.fixture
async def redis_client() -> AsyncGenerator[Redis]:
    client = create_redis()
    yield client
    await client.aclose()


def ledger_for(
    redis: Redis,
    budget: int,
    clock: list[datetime] | None = None,
    *,
    pool: SpendPool = SpendPool.CHAT,
    prefix: str | None = None,
) -> RedisSpendLedger:
    now = clock or [DAY]
    return RedisSpendLedger(
        redis,
        pool=pool,
        daily_budget_micro_usd=budget,
        key_prefix=prefix or f"test_spend:{uuid.uuid4().hex}",
        clock=lambda: now[0],
    )


def worst_case() -> int:
    return cost_micro_usd(prompt_token_ceiling(MESSAGES, None), SAMPLING.max_output_tokens)


class RecordingLedger:
    pool = SpendPool.ANALYSIS

    def __init__(self) -> None:
        self.reserved: list[int] = []
        self.settled: list[int] = []

    async def reserve(self, micro_usd: int) -> Reservation | None:
        self.reserved.append(micro_usd)
        return Reservation(key="k", micro_usd=micro_usd)

    async def settle(self, reservation: Reservation, actual_micro_usd: int) -> None:
        self.settled.append(actual_micro_usd)


class DownLedger:
    pool = SpendPool.ANALYSIS

    async def reserve(self, micro_usd: int) -> Reservation | None:
        raise RedisConnectionError("redis is down")

    async def settle(self, reservation: Reservation, actual_micro_usd: int) -> None:
        raise RedisConnectionError("redis is down")


class RefusingLedger(RecordingLedger):
    async def reserve(self, micro_usd: int) -> Reservation | None:
        return None


class SettleFailsLedger(RecordingLedger):
    async def settle(self, reservation: Reservation, actual_micro_usd: int) -> None:
        raise RedisConnectionError("redis is down")


class GatedGenerator(FakeGenerator):
    def __init__(self, gate: asyncio.Event) -> None:
        super().__init__()
        self._gate = gate

    async def generate(self, messages: list[Message], **kwargs: Any) -> GenerationResult:
        await self._gate.wait()
        return await super().generate(messages, **kwargs)


class FailingGenerator(FakeGenerator):
    def __init__(self, error: Exception) -> None:
        super().__init__()
        self._error = error

    async def generate(self, messages: list[Message], **kwargs: Any) -> GenerationResult:
        raise self._error


def test_the_prompt_ceiling_counts_bytes_not_characters() -> None:
    ascii_only = prompt_token_ceiling([Message(Role.USER, "abcd")], None)
    multibyte = prompt_token_ceiling([Message(Role.USER, "日本語文")], None)
    assert multibyte - ascii_only == 12 - 4


def test_a_response_schema_counts_towards_the_prompt() -> None:
    schema = {"type": "object", "properties": {"x": {"type": "string"}}}
    assert prompt_token_ceiling(MESSAGES, schema) > prompt_token_ceiling(MESSAGES, None)


def test_the_prompt_ceiling_covers_the_strict_schema_a_provider_sends() -> None:
    entry = {"type": "object", "properties": {"t": {"type": "string"}, "u": {"type": "string"}}}
    schema = {"type": "object", "properties": {"a": entry, "b": {"type": "array", "items": entry}}}
    sent = len(json.dumps(strict_schema(schema)).encode())
    assert sent > len(json.dumps(schema).encode())
    assert prompt_token_ceiling(MESSAGES, schema) - prompt_token_ceiling(MESSAGES, None) >= sent


def test_cost_uses_the_configured_prices() -> None:
    expected = (
        1_000_000 * settings.llm_input_usd_per_mtok + 1_000 * settings.llm_output_usd_per_mtok
    )
    assert cost_micro_usd(1_000_000, 1_000) == pytest.approx(expected, abs=1)


async def test_a_call_settles_to_its_actual_cost(redis_client: Redis) -> None:
    ledger = ledger_for(redis_client, budget=1_000_000)
    inner = FakeGenerator(text="one two three")
    result = await BudgetedGenerator(inner, ledger).generate(MESSAGES, sampling=SAMPLING)

    actual = cost_micro_usd(result.usage.prompt_tokens, result.usage.completion_tokens)
    assert actual < worst_case()
    assert await ledger.spent_today() == actual


@pytest.mark.parametrize(
    "error",
    [
        GeneratorUnavailableError("rate limited", status_code=429),
        GenerationRequestError("provider 400", status_code=400),
        GenerationRequestError("provider 404", status_code=404),
        ContextOverflowError("prompt too long", status_code=400),
    ],
)
async def test_a_client_error_status_releases_its_reservation(
    redis_client: Redis, error: Exception
) -> None:
    ledger = ledger_for(redis_client, budget=1_000_000)
    with pytest.raises(type(error)):
        await BudgetedGenerator(FailingGenerator(error), ledger).generate(MESSAGES)
    assert await ledger.spent_today() == 0


@pytest.mark.parametrize(
    "error",
    [
        GeneratorUnavailableError("read timeout"),
        GeneratorUnavailableError("unusable body", status_code=200),
        GeneratorUnavailableError("redirected", status_code=307),
        GeneratorUnavailableError("provider 500", status_code=500),
        GeneratorUnavailableError("gateway 502", status_code=502),
        GeneratorUnavailableError("provider 503", status_code=503),
        GeneratorUnavailableError("gateway 504", status_code=504),
        RuntimeError("bug after the request was sent"),
    ],
)
async def test_a_failure_that_may_have_been_billed_keeps_the_worst_case(
    redis_client: Redis, error: Exception
) -> None:
    ledger = ledger_for(redis_client, budget=1_000_000)
    with pytest.raises(type(error)):
        await BudgetedGenerator(FailingGenerator(error), ledger).generate(
            MESSAGES, sampling=SAMPLING
        )
    assert await ledger.spent_today() == worst_case()


async def test_a_cancelled_call_keeps_the_worst_case(redis_client: Redis) -> None:
    ledger = ledger_for(redis_client, budget=1_000_000)
    guard = BudgetedGenerator(GatedGenerator(asyncio.Event()), ledger)
    task = asyncio.create_task(guard.generate(MESSAGES, sampling=SAMPLING))
    while await ledger.spent_today() == 0:
        await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert await ledger.spent_today() == worst_case()


async def test_a_call_that_would_exceed_the_budget_is_refused_without_calling_the_model(
    redis_client: Redis,
) -> None:
    ledger = ledger_for(redis_client, budget=worst_case() - 1)
    inner = FakeGenerator()
    with pytest.raises(SpendBudgetExceededError):
        await BudgetedGenerator(inner, ledger).generate(MESSAGES, sampling=SAMPLING)
    assert inner.calls == []
    assert await ledger.spent_today() == 0


def test_a_refusal_is_a_provider_outage_to_every_caller() -> None:
    assert issubclass(SpendBudgetExceededError, GeneratorUnavailableError)


async def test_a_refusal_maps_to_its_own_code_in_structured_extraction() -> None:
    guard = BudgetedGenerator(FakeGenerator(), RefusingLedger())
    with pytest.raises(ExtractionError) as caught:
        await _generate(guard, MESSAGES, SAMPLING, {"type": "object"})
    assert caught.value.code == "ai_budget_exhausted"


async def test_a_refusal_names_the_ledger_pool() -> None:
    with pytest.raises(SpendBudgetExceededError) as caught:
        await BudgetedGenerator(FakeGenerator(), RefusingLedger()).generate(MESSAGES)
    assert caught.value.pool is SpendPool.ANALYSIS


async def test_concurrent_reservations_never_overshoot_the_budget(redis_client: Redis) -> None:
    ledger = ledger_for(redis_client, budget=1_000)
    outcomes = await asyncio.gather(*(ledger.reserve(100) for _ in range(50)))
    assert sum(outcome is not None for outcome in outcomes) == 10
    assert await ledger.spent_today() == 1_000


async def test_concurrent_calls_in_flight_never_overshoot_the_budget(redis_client: Redis) -> None:
    allowed = 4
    ledger = ledger_for(redis_client, budget=allowed * worst_case())
    gate = asyncio.Event()
    inner = GatedGenerator(gate)
    guard = BudgetedGenerator(inner, ledger)

    calls = [asyncio.create_task(guard.generate(MESSAGES, sampling=SAMPLING)) for _ in range(20)]
    while sum(task.done() for task in calls) < 20 - allowed:
        await asyncio.sleep(0.01)
    assert await ledger.spent_today() <= allowed * worst_case()
    gate.set()
    results = await asyncio.gather(*calls, return_exceptions=True)

    assert sum(not isinstance(r, BaseException) for r in results) == allowed
    assert all(
        isinstance(r, SpendBudgetExceededError) for r in results if isinstance(r, BaseException)
    )
    assert len(inner.calls) == allowed


async def test_settled_headroom_admits_later_calls(redis_client: Redis) -> None:
    ledger = ledger_for(redis_client, budget=worst_case())
    guard = BudgetedGenerator(FakeGenerator(text="short"), ledger)
    await guard.generate(MESSAGES, sampling=SAMPLING)
    small = SamplingSettings(max_output_tokens=1)
    await guard.generate([Message(Role.USER, "hi")], sampling=small)
    assert await ledger.spent_today() <= worst_case()


async def test_a_new_utc_day_starts_from_zero(redis_client: Redis) -> None:
    clock = [DAY]
    ledger = ledger_for(redis_client, budget=100, clock=clock)
    assert await ledger.reserve(100) is not None
    assert await ledger.reserve(1) is None
    clock[0] = datetime(2026, 10, 16, 0, 0, 1, tzinfo=UTC)
    assert await ledger.reserve(100) is not None


async def test_the_day_key_expires(redis_client: Redis) -> None:
    ledger = ledger_for(redis_client, budget=100)
    reservation = await ledger.reserve(10)
    assert reservation is not None
    assert 0 < await redis_client.ttl(reservation.key) <= 2 * 24 * 3600


async def test_a_settle_after_expiry_does_not_recreate_a_negative_balance(
    redis_client: Redis,
) -> None:
    ledger = ledger_for(redis_client, budget=100)
    reservation = await ledger.reserve(50)
    assert reservation is not None
    await redis_client.delete(reservation.key)
    await ledger.settle(reservation, 0)
    assert await redis_client.exists(reservation.key) == 0


async def test_redis_down_fails_closed_without_calling_the_model() -> None:
    inner = FakeGenerator()
    with pytest.raises(GeneratorUnavailableError):
        await BudgetedGenerator(inner, DownLedger()).generate(MESSAGES)
    assert inner.calls == []


async def test_a_failed_settle_still_returns_the_paid_answer(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING):
        result = await BudgetedGenerator(FakeGenerator(text="ok"), SettleFailsLedger()).generate(
            MESSAGES
        )
    assert result.text == "ok"
    assert "settle failed" in caplog.text


async def test_no_sampling_reserves_the_default_output_ceiling() -> None:
    ledger = RecordingLedger()
    await BudgetedGenerator(FakeGenerator(), ledger).generate(MESSAGES)
    default = SamplingSettings().max_output_tokens
    assert ledger.reserved == [cost_micro_usd(prompt_token_ceiling(MESSAGES, None), default)]


async def test_crossing_eighty_percent_warns_once_and_never_logs_content(
    redis_client: Redis, caplog: pytest.LogCaptureFixture
) -> None:
    ledger = ledger_for(redis_client, budget=1_000)
    with caplog.at_level(logging.WARNING, logger="app.core.spend_ledger"):
        for _ in range(7):
            await ledger.reserve(100)
        assert "passed" not in caplog.text
        await ledger.reserve(100)
        await ledger.reserve(100)
        await ledger.reserve(50)
        await ledger.reserve(500)
        await ledger.reserve(500)
    assert caplog.text.count("passed 80% of budget") == 1
    assert caplog.text.count("budget exhausted") == 1


async def test_one_oversized_refusal_is_not_reported_as_an_exhausted_budget(
    redis_client: Redis, caplog: pytest.LogCaptureFixture
) -> None:
    ledger = ledger_for(redis_client, budget=1_000)
    with caplog.at_level(logging.DEBUG, logger="app.core.spend_ledger"):
        assert await ledger.reserve(100) is not None
        assert await ledger.reserve(5_000) is None
    assert "budget exhausted" not in caplog.text
    assert "reservation refused pool=chat reserved_micro_usd=5000" in caplog.text
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


async def test_an_early_oversized_refusal_does_not_mute_the_real_exhaustion_warning(
    redis_client: Redis, caplog: pytest.LogCaptureFixture
) -> None:
    ledger = ledger_for(redis_client, budget=1_000)
    with caplog.at_level(logging.WARNING, logger="app.core.spend_ledger"):
        assert await ledger.reserve(5_000) is None
        assert await ledger.reserve(960) is not None
        assert await ledger.reserve(100) is None
        assert await ledger.reserve(100) is None
    assert caplog.text.count("budget exhausted pool=chat") == 1


async def test_the_pools_are_separate_budgets_under_one_hash_tag(redis_client: Redis) -> None:
    prefix = f"test_spend:{uuid.uuid4().hex}"
    chat = ledger_for(redis_client, budget=100, prefix=prefix, pool=SpendPool.CHAT)
    analysis = ledger_for(redis_client, budget=100, prefix=prefix, pool=SpendPool.ANALYSIS)

    analysed = await analysis.reserve(100)
    assert analysed is not None
    assert await analysis.reserve(1) is None
    chatted = await chat.reserve(100)

    assert chatted is not None
    assert chatted.key != analysed.key
    tag = f"{{{prefix}:{DAY.date().isoformat()}}}"
    assert chatted.key == f"{tag}:chat:spent"
    assert analysed.key == f"{tag}:analysis:spent"


async def test_guard_logs_never_carry_message_content(
    redis_client: Redis, caplog: pytest.LogCaptureFixture
) -> None:
    ledger = ledger_for(redis_client, budget=1)
    with caplog.at_level(logging.DEBUG), pytest.raises(SpendBudgetExceededError):
        await BudgetedGenerator(FakeGenerator(), ledger).generate(MESSAGES)
    assert SECRET not in caplog.text


async def test_the_guard_keeps_the_inner_model_name_and_forwards_aclose() -> None:
    class Closable(FakeGenerator):
        closed = False

        async def aclose(self) -> None:
            self.closed = True

    inner = Closable()
    guard = BudgetedGenerator(inner, RecordingLedger())
    await guard.aclose()
    assert guard.model_name == inner.model_name
    assert inner.closed


async def test_guarded_wraps_only_when_enabled(
    redis_client: Redis, monkeypatch: pytest.MonkeyPatch
) -> None:
    inner = FakeGenerator()
    assert isinstance(guarded(inner, redis_client, SpendPool.CHAT), BudgetedGenerator)
    monkeypatch.setattr(settings, "llm_spend_guard_enabled", False)
    assert guarded(inner, redis_client, SpendPool.CHAT) is inner


@pytest.mark.parametrize(
    ("pool", "setting"),
    [
        (SpendPool.CHAT, "llm_daily_budget_chat_usd"),
        (SpendPool.ANALYSIS, "llm_daily_budget_analysis_usd"),
    ],
)
async def test_each_pool_is_held_to_its_own_budget(
    redis_client: Redis, monkeypatch: pytest.MonkeyPatch, pool: SpendPool, setting: str
) -> None:
    monkeypatch.setattr(settings, setting, 0.25)
    guard = guarded(FakeGenerator(), redis_client, pool)
    assert isinstance(guard, BudgetedGenerator)
    ledger = guard._ledger
    assert isinstance(ledger, RedisSpendLedger)
    assert daily_budget_usd(pool) == 0.25
    assert ledger._budget == 250_000
    assert ledger._pool is pool


def test_the_startup_log_states_the_budget_and_prices(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(settings, "llm_spend_guard_enabled", True)
    with caplog.at_level(logging.INFO, logger="app.ai.spend_guard"):
        log_spend_guard_config(SpendPool.ANALYSIS)
    assert "pool=analysis" in caplog.text
    assert f"daily_budget_usd={settings.llm_daily_budget_analysis_usd:.2f}" in caplog.text
    assert "input_usd_per_mtok=" in caplog.text
    assert "output_usd_per_mtok=" in caplog.text


@pytest.mark.parametrize(("provider", "warns"), [("openai", True), ("ollama", False)])
def test_a_disabled_guard_warns_only_when_the_provider_bills(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, provider: str, warns: bool
) -> None:
    monkeypatch.setattr(settings, "llm_spend_guard_enabled", False)
    monkeypatch.setattr(settings, "generation_provider", provider)
    with caplog.at_level(logging.INFO, logger="app.ai.spend_guard"):
        log_spend_guard_config(SpendPool.CHAT)
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert bool(warnings) is warns
    assert "daily_budget_usd" not in caplog.text


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (datetime(2026, 10, 15, 0, 0, tzinfo=UTC), 86_400),
        (datetime(2026, 10, 15, 23, 59, 30, tzinfo=UTC), 30),
        (datetime(2026, 10, 15, 23, 59, 59, 999_000, tzinfo=UTC), 1),
        (datetime(2026, 10, 15, 12, 0, tzinfo=timezone(timedelta(hours=-5))), 7 * 3600),
    ],
)
def test_the_reset_is_the_next_utc_midnight(now: datetime, expected: int) -> None:
    assert seconds_until_reset(now) == expected
