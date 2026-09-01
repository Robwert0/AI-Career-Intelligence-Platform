import json
import os
from typing import Any

import httpx
import pytest
from fakes import FakeGenerator
from pydantic import ValidationError

from app.ai.generation import (
    FinishReason,
    GenerationRequestError,
    Generator,
    GeneratorUnavailableError,
    Message,
    Role,
    SamplingSettings,
    TokenLogprob,
)
from app.ai.ollama import OllamaGenerator

MESSAGES = [
    Message(Role.SYSTEM, "Answer in exactly one word."),
    Message(Role.USER, "Capital of France?"),
]

LOGPROBS = [
    {
        "token": "Paris",
        "logprob": -0.05,
        "bytes": [80, 97, 114, 105, 115],
        "top_logprobs": [
            {"token": "Paris", "logprob": -0.05, "bytes": []},
            {"token": "France", "logprob": -17.03, "bytes": []},
        ],
    }
]


def ollama_body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "model": "qwen3:8b",
        "created_at": "2026-08-28T11:58:31.575776894Z",
        "message": {"role": "assistant", "content": "Paris"},
        "done": True,
        "done_reason": "stop",
        "total_duration": 7164826410,
        "load_duration": 6680770990,
        "prompt_eval_count": 31,
        "prompt_eval_duration": 376029000,
        "eval_count": 2,
        "eval_duration": 89196000,
    }
    return body | overrides


def stub(
    body: dict[str, Any] | None = None,
    *,
    status: int = 200,
    raises: Exception | None = None,
) -> tuple[OllamaGenerator, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if raises is not None:
            raise raises
        return httpx.Response(status, json=body if body is not None else ollama_body())

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://ollama.test"
    )
    return OllamaGenerator(client=client, model="qwen3:8b"), seen


def sent_body(seen: list[httpx.Request]) -> dict[str, Any]:
    payload: dict[str, Any] = json.loads(seen[0].content)
    return payload


def test_both_generators_satisfy_the_generator_protocol() -> None:
    generator, _ = stub()
    generators: list[Generator] = [FakeGenerator(), generator]
    assert [g.model_name for g in generators] == ["fake-generator", "ollama/qwen3:8b"]


async def test_messages_are_sent_as_ordered_role_content_pairs() -> None:
    generator, seen = stub()
    await generator.generate(MESSAGES)
    assert sent_body(seen)["messages"] == [
        {"role": "system", "content": "Answer in exactly one word."},
        {"role": "user", "content": "Capital of France?"},
    ]


async def test_every_sampling_knob_reaches_the_wire_under_its_provider_name() -> None:
    generator, seen = stub()
    await generator.generate(
        MESSAGES,
        sampling=SamplingSettings(
            temperature=0.7, top_p=0.9, top_k=40, seed=42, max_output_tokens=64
        ),
    )
    assert sent_body(seen)["options"] == {
        "temperature": 0.7,
        "top_p": 0.9,
        "top_k": 40,
        "seed": 42,
        "num_predict": 64,
    }


async def test_unset_knobs_are_omitted_rather_than_sent_as_null() -> None:
    generator, seen = stub()
    await generator.generate(MESSAGES, sampling=SamplingSettings(temperature=0.0))
    options = sent_body(seen)["options"]
    assert "top_k" not in options
    assert "seed" not in options


async def test_the_request_does_not_stream() -> None:
    generator, seen = stub()
    await generator.generate(MESSAGES)
    assert sent_body(seen)["stream"] is False


async def test_reasoning_is_disabled_so_it_cannot_consume_the_output_budget() -> None:
    generator, seen = stub()
    await generator.generate(MESSAGES)
    assert sent_body(seen)["think"] is False


async def test_logprobs_are_not_requested_unless_asked_for() -> None:
    generator, seen = stub()
    await generator.generate(MESSAGES)
    assert "logprobs" not in sent_body(seen)


async def test_asking_for_logprobs_requests_them_with_the_alternative_count() -> None:
    generator, seen = stub()
    await generator.generate(MESSAGES, top_logprobs=2)
    body = sent_body(seen)
    assert body["logprobs"] is True
    assert body["top_logprobs"] == 2


async def test_the_answer_text_and_a_stop_reason_come_back() -> None:
    generator, _ = stub()
    result = await generator.generate(MESSAGES)
    assert result.text == "Paris"
    assert result.finish_reason is FinishReason.STOP
    assert result.truncated is False


async def test_usage_is_taken_from_the_provider_token_counts() -> None:
    generator, _ = stub()
    result = await generator.generate(MESSAGES)
    assert result.usage.prompt_tokens == 31
    assert result.usage.completion_tokens == 2


async def test_the_result_names_the_generator_not_just_the_bare_model() -> None:
    generator, _ = stub()
    result = await generator.generate(MESSAGES)
    assert result.model == generator.model_name


async def test_latency_is_measured_as_a_whole_number_of_milliseconds() -> None:
    generator, _ = stub()
    result = await generator.generate(MESSAGES)
    assert isinstance(result.latency_ms, int)
    assert result.latency_ms >= 0


async def test_the_result_echoes_the_settings_that_produced_it() -> None:
    generator, _ = stub()
    sampling = SamplingSettings(temperature=1.2, seed=7)
    result = await generator.generate(MESSAGES, sampling=sampling)
    assert result.sampling == sampling


async def test_defaults_are_echoed_when_no_sampling_is_passed() -> None:
    generator, _ = stub()
    result = await generator.generate(MESSAGES)
    assert result.sampling == SamplingSettings()


async def test_hitting_the_token_limit_is_reported_as_truncation() -> None:
    generator, _ = stub(ollama_body(done_reason="length"))
    result = await generator.generate(MESSAGES)
    assert result.finish_reason is FinishReason.LENGTH
    assert result.truncated is True


async def test_an_empty_answer_eaten_by_reasoning_still_reports_truncation() -> None:
    generator, _ = stub(
        ollama_body(
            done_reason="length",
            message={"role": "assistant", "content": "", "thinking": "Let me think..."},
        )
    )
    result = await generator.generate(MESSAGES)
    assert result.text == ""
    assert result.truncated is True
    assert result.thinking == "Let me think..."


async def test_reasoning_text_never_leaks_into_the_answer() -> None:
    generator, _ = stub(
        ollama_body(message={"role": "assistant", "content": "Paris", "thinking": "France..."})
    )
    result = await generator.generate(MESSAGES)
    assert result.text == "Paris"
    assert result.thinking == "France..."


async def test_an_unrecognised_finish_reason_is_not_mistaken_for_success() -> None:
    generator, _ = stub(ollama_body(done_reason="something-new"))
    result = await generator.generate(MESSAGES)
    assert result.finish_reason is FinishReason.OTHER


async def test_a_missing_finish_reason_is_not_mistaken_for_success() -> None:
    body = ollama_body()
    del body["done_reason"]
    generator, _ = stub(body)
    result = await generator.generate(MESSAGES)
    assert result.finish_reason is FinishReason.OTHER


async def test_logprobs_are_absent_when_they_were_not_requested() -> None:
    generator, _ = stub()
    result = await generator.generate(MESSAGES)
    assert result.logprobs is None


async def test_logprobs_are_mapped_with_their_alternatives() -> None:
    generator, _ = stub(ollama_body(logprobs=LOGPROBS))
    result = await generator.generate(MESSAGES, top_logprobs=2)
    assert result.logprobs == (
        TokenLogprob("Paris", -0.05, (("Paris", -0.05), ("France", -17.03))),
    )


async def test_a_refused_connection_is_reported_as_unavailable() -> None:
    generator, _ = stub(raises=httpx.ConnectError("connection refused"))
    with pytest.raises(GeneratorUnavailableError):
        await generator.generate(MESSAGES)


async def test_a_timeout_is_reported_as_unavailable() -> None:
    generator, _ = stub(raises=httpx.ReadTimeout("timed out"))
    with pytest.raises(GeneratorUnavailableError):
        await generator.generate(MESSAGES)


async def test_a_provider_side_failure_is_reported_as_unavailable() -> None:
    generator, _ = stub({"error": "internal"}, status=500)
    with pytest.raises(GeneratorUnavailableError):
        await generator.generate(MESSAGES)


async def test_a_rejected_request_is_not_reported_as_a_transient_outage() -> None:
    generator, _ = stub({"error": "model 'does-not-exist' not found"}, status=404)
    with pytest.raises(GenerationRequestError, match="does-not-exist"):
        await generator.generate(MESSAGES)


async def test_generating_without_messages_is_rejected_before_any_call() -> None:
    generator, seen = stub()
    with pytest.raises(ValueError):
        await generator.generate([])
    assert seen == []


@pytest.mark.parametrize(
    "kwargs",
    [
        {"temperature": -0.1},
        {"temperature": 2.5},
        {"top_p": 0.0},
        {"top_p": 1.5},
        {"top_k": 0},
        {"max_output_tokens": 0},
    ],
)
def test_out_of_range_sampling_settings_are_rejected(kwargs: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        SamplingSettings(**kwargs)


def test_sampling_settings_cannot_be_mutated_after_a_result_records_them() -> None:
    sampling = SamplingSettings(temperature=0.5)
    with pytest.raises(ValidationError):
        sampling.temperature = 1.0  # type: ignore[misc]


async def test_the_fake_records_the_messages_it_was_given() -> None:
    fake = FakeGenerator()
    await fake.generate(MESSAGES)
    assert fake.calls == [MESSAGES]


async def test_the_fake_returns_the_same_result_for_the_same_messages() -> None:
    fake = FakeGenerator()
    first = await fake.generate(MESSAGES)
    second = await fake.generate(MESSAGES)
    assert first == second


async def test_the_fake_can_be_told_to_truncate_so_callers_can_test_that_path() -> None:
    fake = FakeGenerator(finish_reason=FinishReason.LENGTH)
    assert (await fake.generate(MESSAGES)).truncated is True


@pytest.mark.skipif(
    os.environ.get("OLLAMA_LIVE") != "1",
    reason="needs a running Ollama; set OLLAMA_LIVE=1",
)
async def test_a_live_ollama_answers_and_reports_what_it_spent() -> None:
    generator = OllamaGenerator()
    try:
        result = await generator.generate(MESSAGES, sampling=SamplingSettings(max_output_tokens=16))
    finally:
        await generator.aclose()
    # Never assert on the words: identical settings produce different wordings.
    assert result.text.strip()
    assert result.finish_reason in (FinishReason.STOP, FinishReason.LENGTH)
    assert result.usage.prompt_tokens > 0
    assert result.usage.completion_tokens > 0
