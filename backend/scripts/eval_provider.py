"""Picks the model an eval script talks to, and meters what it spent.

The provider is a flag, not GENERATION_PROVIDER, so an eval never bills OpenAI unless asked to.
It is deliberately not wrapped in the spend guard: the guard's daily pools are the live budget
visitors draw on, and a local eval would drain it (or be cut off by it halfway through a run).
The run's cost is bounded by its fixed cases and printed instead.
"""

import argparse
from typing import Any, Literal

from app.ai.generation import ClosableGenerator, GenerationResult, Message, SamplingSettings
from app.ai.ollama import OllamaGenerator
from app.ai.openai import OpenAIGenerator
from app.ai.spend_guard import cost_micro_usd

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
    if any(model.startswith("openai/") for model in models):
        line += f" cost_usd={cost_micro_usd(prompt, completion) / 1_000_000:.4f}"
    return line
