import argparse
import sys
from pathlib import Path

import pytest
from pydantic import SecretStr

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))

from eval_provider import (  # noqa: E402
    MeteredGenerator,
    add_provider_arguments,
    build_provider,
    usage_line,
)
from fakes import FakeGenerator  # noqa: E402

from app.ai.generation import Message, Role  # noqa: E402
from app.ai.ollama import OllamaGenerator  # noqa: E402
from app.ai.openai import OpenAIGenerator  # noqa: E402
from app.core.config import settings  # noqa: E402


class OpenAINamedGenerator(FakeGenerator):
    @property
    def model_name(self) -> str:
        return "openai/gpt-6-luna"


def parse(*argv: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    add_provider_arguments(parser)
    return parser.parse_args(argv)


def test_the_paid_provider_is_opt_in() -> None:
    args = parse()

    assert (args.provider, args.model) == ("ollama", None)


async def test_build_provider_honours_the_model_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "openai_api_key", None)
    ollama = build_provider("ollama", "llama3:8b", timeout_seconds=5)
    try:
        assert isinstance(ollama, OllamaGenerator)
        assert ollama.model_name.endswith("llama3:8b")
    finally:
        await ollama.aclose()
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        build_provider("openai", "gpt-6-luna", timeout_seconds=5)


async def test_build_provider_builds_openai_unguarded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "openai_api_key", SecretStr("sk-test"))
    openai = build_provider("openai", "gpt-6-luna", timeout_seconds=5)
    try:
        assert isinstance(openai, OpenAIGenerator)
        assert openai.model_name == "openai/gpt-6-luna"
    finally:
        await openai.aclose()


async def test_metered_generator_sums_usage_across_calls() -> None:
    metered = MeteredGenerator(FakeGenerator("two words"))

    await metered.generate([Message(Role.USER, "one two three")])
    await metered.generate([Message(Role.USER, "four")])

    assert (metered.calls, metered.prompt_tokens, metered.completion_tokens) == (2, 4, 4)


async def test_usage_line_prices_only_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "openai_chat_model", "gpt-6-luna")
    monkeypatch.setattr(settings, "llm_input_usd_per_mtok", 0.10)
    monkeypatch.setattr(settings, "llm_output_usd_per_mtok", 0.50)
    local = MeteredGenerator(FakeGenerator())
    paid = MeteredGenerator(OpenAINamedGenerator("x " * 1000))
    await local.generate([Message(Role.USER, "hello")])
    await paid.generate([Message(Role.USER, "hello " * 1000)])

    assert "cost_usd" not in usage_line([local])
    assert usage_line([paid]).endswith("cost_usd=0.0006 priced_at=0.10/0.50 per Mtok")


async def test_usage_line_refuses_to_price_an_overridden_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "openai_chat_model", "gpt-6-mini")
    paid = MeteredGenerator(OpenAINamedGenerator("x " * 1000))
    await paid.generate([Message(Role.USER, "hello " * 1000)])

    line = usage_line([paid])

    assert line.endswith("cost_usd=unknown (prices are for openai/gpt-6-mini)")
    assert "priced_at" not in line
