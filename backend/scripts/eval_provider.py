"""Picks the model an eval script talks to, and meters what it spent.

The provider is a flag, not GENERATION_PROVIDER, so an eval never bills OpenAI unless asked to.
It is deliberately not wrapped in the spend guard: the guard's daily pools are the live budget
visitors draw on, and a local eval would drain it (or be cut off by it halfway through a run).
Instead, the run's token usage is printed, priced only when the prices in settings are known
to belong to the model that ran.
"""

import argparse
from typing import Any, Literal

from app.ai.generation import ClosableGenerator, GenerationResult, Message, SamplingSettings
from app.ai.ollama import OllamaGenerator
from app.ai.openai import OpenAIGenerator
from app.ai.spend_guard import cost_micro_usd
from app.core.config import settings

Provider = Literal["ollama", "openai"]


def add_provider_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--provider",
        choices=("ollama", "openai"),
        default="ollama",
        help="ollama (default, free) or openai (billed, outside the daily spend pools)",
    )
    parser.add_argument(
        "--model", default=None, help="overrides GENERATION_MODEL or OPENAI_CHAT_MODEL"
    )


class MeteredGenerator:
    def __init__(self, inner: ClosableGenerator) -> None:
        self._inner = inner
        self.calls = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0

    @property
    def model_name(self) -> str:
        return self._inner.model_name

    async def generate(
        self,
        messages: list[Message],
        *,
        sampling: SamplingSettings | None = None,
        top_logprobs: int | None = None,
        response_schema: dict[str, Any] | None = None,
    ) -> GenerationResult:
        self.calls += 1
        result = await self._inner.generate(
            messages, sampling=sampling, top_logprobs=top_logprobs, response_schema=response_schema
        )
        self.prompt_tokens += result.usage.prompt_tokens
        self.completion_tokens += result.usage.completion_tokens
        return result

    async def aclose(self) -> None:
        await self._inner.aclose()


def build_provider(
    provider: Provider, model: str | None, timeout_seconds: int
) -> ClosableGenerator:
    if provider == "openai":
        return OpenAIGenerator(model=model, timeout_seconds=timeout_seconds)
    return OllamaGenerator(model=model, timeout_seconds=timeout_seconds)


def usage_line(generators: list[MeteredGenerator]) -> str:
    prompt = sum(g.prompt_tokens for g in generators)
    completion = sum(g.completion_tokens for g in generators)
    calls = sum(g.calls for g in generators)
    models = sorted({g.model_name for g in generators})
    line = f"model={','.join(models)} calls={calls} prompt_tokens={prompt} "
    line += f"completion_tokens={completion}"
    paid = [g for g in generators if g.model_name.startswith("openai/")]
    if not paid:
        return line
    configured = f"openai/{settings.openai_chat_model}"
    # The LLM_*_USD_PER_MTOK prices are those of OPENAI_CHAT_MODEL; --model does not change them.
    if any(g.model_name != configured for g in paid):
        return line + f" cost_usd=unknown (prices are for {configured})"
    cost = cost_micro_usd(
        sum(g.prompt_tokens for g in paid), sum(g.completion_tokens for g in paid)
    )
    line += f" cost_usd={cost / 1_000_000:.4f}"
    line += f" priced_at={settings.llm_input_usd_per_mtok:.2f}/"
    return line + f"{settings.llm_output_usd_per_mtok:.2f} per Mtok"
