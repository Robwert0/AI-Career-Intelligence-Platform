import json
import logging
import math
from typing import Any, Protocol

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.ai.generation import (
    GenerationRequestError,
    GenerationResult,
    Generator,
    GeneratorUnavailableError,
    Message,
    SamplingSettings,
)
from app.ai.json_schema import strict_schema
from app.core.config import settings
from app.core.spend_ledger import RedisSpendLedger, Reservation, SpendPool

logger = logging.getLogger(__name__)

# Chat-template tokens around each message; generous on purpose.
MESSAGE_OVERHEAD_TOKENS = 8


class SpendBudgetExceededError(GeneratorUnavailableError):
    """The global daily LLM budget is spent; callers treat it like any provider outage."""


class SpendLedger(Protocol):
    async def reserve(self, micro_usd: int) -> Reservation | None: ...

    async def settle(self, reservation: Reservation, actual_micro_usd: int) -> None: ...


def prompt_token_ceiling(messages: list[Message], response_schema: dict[str, Any] | None) -> int:
    # Byte-level BPE never emits more tokens than input bytes, so UTF-8 length is an upper bound.
    tokens = sum(len(m.content.encode()) + MESSAGE_OVERHEAD_TOKENS for m in messages)
    if response_schema is not None:
        # A strict-mode provider sends the tightened schema, which is the larger of the two.
        tokens += max(
            len(json.dumps(schema).encode())
            for schema in (response_schema, strict_schema(response_schema))
        )
    return tokens


def cost_micro_usd(prompt_tokens: int, completion_tokens: int) -> int:
    # USD per million tokens times tokens is exactly micro-dollars.
    return math.ceil(
        prompt_tokens * settings.llm_input_usd_per_mtok
        + completion_tokens * settings.llm_output_usd_per_mtok
    )


class BudgetedGenerator:
    def __init__(self, inner: Generator, ledger: SpendLedger) -> None:
        self._inner = inner
        self._ledger = ledger

    @property
    def model_name(self) -> str:
        return self._inner.model_name

    async def aclose(self) -> None:
        close = getattr(self._inner, "aclose", None)
        if close is not None:
            await close()

    async def generate(
        self,
        messages: list[Message],
        *,
        sampling: SamplingSettings | None = None,
        top_logprobs: int | None = None,
        response_schema: dict[str, Any] | None = None,
    ) -> GenerationResult:
        max_output = (sampling or SamplingSettings()).max_output_tokens
        reservation = await self._reserve(
            cost_micro_usd(prompt_token_ceiling(messages, response_schema), max_output)
        )
        try:
            result = await self._inner.generate(
                messages,
                sampling=sampling,
                top_logprobs=top_logprobs,
                response_schema=response_schema,
            )
        except (GenerationRequestError, GeneratorUnavailableError) as exc:
            if _provider_refused(exc):
                await self._settle(reservation, 0)
            raise
        usage = result.usage
        await self._settle(
            reservation, cost_micro_usd(usage.prompt_tokens, usage.completion_tokens)
        )
        return result

    async def _reserve(self, micro_usd: int) -> Reservation:
        try:
            reservation = await self._ledger.reserve(micro_usd)
        except RedisError:
            logger.warning("llm spend ledger unavailable; refusing the call")
            raise GeneratorUnavailableError("spend ledger unavailable") from None
        if reservation is None:
            raise SpendBudgetExceededError("daily LLM budget exhausted")
        return reservation

    async def _settle(self, reservation: Reservation, actual_micro_usd: int) -> None:
        # A failed settle leaves the worst-case reservation booked: over-counting is the safe side.
        try:
            await self._ledger.settle(reservation, actual_micro_usd)
        except RedisError:
            logger.warning(
                "llm spend settle failed; reservation kept reserved_micro_usd=%d",
                reservation.micro_usd,
            )


def _provider_refused(exc: GenerationRequestError | GeneratorUnavailableError) -> bool:
    # Only a 4xx proves nothing was billed. A 5xx can come from a gateway after the provider
    # already generated, and a timeout, cancellation or dropped connection may have been charged
    # in full, so those keep the worst case booked.
    return exc.status_code is not None and 400 <= exc.status_code < 500


def daily_budget_usd(pool: SpendPool) -> float:
    match pool:
        case SpendPool.CHAT:
            return settings.llm_daily_budget_chat_usd
        case SpendPool.ANALYSIS:
            return settings.llm_daily_budget_analysis_usd


def guarded[G: Generator](generator: G, redis: Redis, pool: SpendPool) -> G | BudgetedGenerator:
    if not settings.llm_spend_guard_enabled:
        return generator
    ledger = RedisSpendLedger(
        redis,
        pool=pool,
        daily_budget_micro_usd=math.floor(daily_budget_usd(pool) * 1_000_000),
    )
    return BudgetedGenerator(generator, ledger)


def log_spend_guard_config(pool: SpendPool) -> None:
    if not settings.llm_spend_guard_enabled:
        if settings.generation_provider == "openai":
            logger.warning(
                "llm spend guard disabled with generation_provider=openai; no daily budget "
                "caps the bill pool=%s",
                pool,
            )
        return
    logger.info(
        "llm spend guard pool=%s daily_budget_usd=%.2f input_usd_per_mtok=%.4f "
        "output_usd_per_mtok=%.4f",
        pool,
        daily_budget_usd(pool),
        settings.llm_input_usd_per_mtok,
        settings.llm_output_usd_per_mtok,
    )
