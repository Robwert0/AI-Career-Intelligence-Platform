import copy
import json
import os
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from app.ai import generators
from app.ai.generation import (
    ContextOverflowError,
    FinishReason,
    GenerationRequestError,
    Generator,
    GeneratorUnavailableError,
    Message,
    Role,
    SamplingSettings,
    TokenLogprob,
    Usage,
)
from app.ai.ollama import OllamaGenerator
from app.ai.openai import OpenAIGenerator, strict_schema
from app.core.config import settings

MESSAGES = [
    Message(Role.SYSTEM, "Answer in exactly one word."),
    Message(Role.USER, "Capital of France?"),
]
KEY = "sk-test-0123456789abcdefSECRET"


def openai_body(**message: Any) -> dict[str, Any]:
    return {
        "id": "chatcmpl-1",
        "model": "gpt-6-luna",
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {"role": "assistant", "content": "Paris", "refusal": None} | message,
            }
        ],
        "usage": {"prompt_tokens": 19, "completion_tokens": 4, "total_tokens": 23},
    }


def stub(
    body: dict[str, Any] | None = None,
    *,
    status: int = 200,
    raises: Exception | None = None,
    text: str | None = None,
    headers: dict[str, str] | None = None,
    reasoning_effort: str | None = "none",
) -> tuple[OpenAIGenerator, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if raises is not None:
            raise raises
        if text is not None:
            return httpx.Response(status, text=text, headers=headers)
        if headers is not None and body is None:
            return httpx.Response(status, headers=headers)
        return httpx.Response(status, json=body if body is not None else openai_body())

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://openai.test/v1",
        headers={"Authorization": f"Bearer {KEY}"},
    )
    generator = OpenAIGenerator(client=client, model="gpt-6-luna")
    generator._reasoning_effort = reasoning_effort
    return generator, seen


def sent_body(seen: list[httpx.Request]) -> dict[str, Any]:
    payload: dict[str, Any] = json.loads(seen[0].content)
    return payload


def api_error(code: str | None, message: str = "Incorrect API key provided: sk-tes****CRET") -> Any:
    return {
        "error": {"message": message, "type": "invalid_request_error", "param": None, "code": code}
    }


def test_it_satisfies_the_generator_protocol() -> None:
    generator, _ = stub()
    as_protocol: Generator = generator
    assert as_protocol.model_name == "openai/gpt-6-luna"


async def test_it_posts_ordered_messages_to_chat_completions() -> None:
    generator, seen = stub()
    await generator.generate(MESSAGES)
    assert seen[0].url.path == "/v1/chat/completions"
    assert sent_body(seen)["model"] == "gpt-6-luna"
    assert sent_body(seen)["messages"] == [
        {"role": "system", "content": "Answer in exactly one word."},
        {"role": "user", "content": "Capital of France?"},
    ]


async def test_the_key_travels_as_a_bearer_header() -> None:
    generator, seen = stub()
    await generator.generate(MESSAGES)
    assert seen[0].headers["authorization"] == f"Bearer {KEY}"


async def test_sampling_reaches_the_wire_under_openai_names() -> None:
    generator, seen = stub()
    await generator.generate(
        MESSAGES,
        sampling=SamplingSettings(temperature=0.7, top_p=0.9, seed=42, max_output_tokens=64),
    )
    body = sent_body(seen)
    assert {
        key: body[key] for key in ("temperature", "top_p", "seed", "max_completion_tokens")
    } == {
        "temperature": 0.7,
        "top_p": 0.9,
        "seed": 42,
        "max_completion_tokens": 64,
    }


async def test_an_unset_seed_is_omitted() -> None:
    generator, seen = stub()
    await generator.generate(MESSAGES)
    assert "seed" not in sent_body(seen)


async def test_top_k_is_refused_rather_than_silently_dropped() -> None:
    generator, seen = stub()
    with pytest.raises(GenerationRequestError, match="top_k"):
        await generator.generate(MESSAGES, sampling=SamplingSettings(top_k=40))
    assert seen == []


async def test_reasoning_effort_is_sent_when_configured() -> None:
    generator, seen = stub(reasoning_effort="none")
    await generator.generate(MESSAGES)
    assert sent_body(seen)["reasoning_effort"] == "none"


async def test_reasoning_effort_is_omitted_for_models_without_it() -> None:
    generator, seen = stub(reasoning_effort=None)
    await generator.generate(MESSAGES)
    assert "reasoning_effort" not in sent_body(seen)


async def test_the_result_carries_text_usage_and_finish_reason() -> None:
    generator, _ = stub()
    result = await generator.generate(MESSAGES)
    assert result.text == "Paris"
    assert result.finish_reason is FinishReason.STOP
    assert result.usage == Usage(19, 4)
    assert result.model == "openai/gpt-6-luna"
    assert result.logprobs is None
    assert result.thinking is None


async def test_a_length_stop_is_reported_as_truncated() -> None:
    body = openai_body()
    body["choices"][0]["finish_reason"] = "length"
    generator, _ = stub(body)
    result = await generator.generate(MESSAGES)
    assert result.truncated


async def test_a_content_filter_stop_is_reported_as_filtered() -> None:
    body = openai_body()
    body["choices"][0]["finish_reason"] = "content_filter"
    generator, _ = stub(body)
    assert (await generator.generate(MESSAGES)).finish_reason is FinishReason.CONTENT_FILTER


async def test_an_unknown_finish_is_other() -> None:
    body = openai_body()
    body["choices"][0]["finish_reason"] = "tool_calls"
    generator, _ = stub(body)
    assert (await generator.generate(MESSAGES)).finish_reason is FinishReason.OTHER


async def test_a_refusal_comes_back_as_text_with_finish_refusal() -> None:
    generator, _ = stub(openai_body(content=None, refusal="I can't help with that."))
    result = await generator.generate(MESSAGES)
    assert result.text == "I can't help with that."
    assert result.finish_reason is FinishReason.REFUSAL


async def test_a_refusal_beside_content_is_still_a_refusal() -> None:
    generator, _ = stub(openai_body(content="Partial", refusal="I can't help with that."))
    assert (await generator.generate(MESSAGES)).finish_reason is FinishReason.REFUSAL


async def test_logprobs_are_requested_and_mapped() -> None:
    body = openai_body()
    body["choices"][0]["logprobs"] = {
        "content": [
            {
                "token": "Paris",
                "logprob": -0.05,
                "bytes": [80],
                "top_logprobs": [
                    {"token": "Paris", "logprob": -0.05, "bytes": []},
                    {"token": "France", "logprob": -17.0, "bytes": []},
                ],
            }
        ]
    }
    generator, seen = stub(body)
    result = await generator.generate(MESSAGES, top_logprobs=2)
    assert sent_body(seen)["logprobs"] is True
    assert sent_body(seen)["top_logprobs"] == 2
    assert result.logprobs == (TokenLogprob("Paris", -0.05, (("Paris", -0.05), ("France", -17.0))),)


async def test_a_response_schema_is_sent_as_strict_json_schema() -> None:
    generator, seen = stub()
    schema = {"type": "object", "properties": {"city": {"type": "string"}}}
    await generator.generate(MESSAGES, response_schema=schema)
    assert sent_body(seen)["response_format"] == {
        "type": "json_schema",
        "json_schema": {
            "name": "reply",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": ["city"],
                "additionalProperties": False,
            },
        },
    }


def test_strict_schema_requires_every_property_including_nested_defs() -> None:
    schema = {
        "type": "object",
        "properties": {
            "company": {"anyOf": [{"type": "string"}, {"type": "null"}], "default": None},
            "items": {"type": "array", "items": {"$ref": "#/$defs/Entry"}},
        },
        "required": ["items"],
        "$defs": {
            "Entry": {
                "type": "object",
                "properties": {"text": {"type": "string"}, "links": {"type": "array"}},
                "required": ["text"],
            }
        },
    }
    strict = strict_schema(schema)
    assert strict["required"] == ["company", "items"]
    assert strict["additionalProperties"] is False
    assert strict["$defs"]["Entry"]["required"] == ["text", "links"]
    assert strict["$defs"]["Entry"]["additionalProperties"] is False


def test_strict_schema_leaves_the_callers_schema_untouched() -> None:
    schema = {"type": "object", "properties": {"a": {"type": "string"}}, "required": []}
    before = copy.deepcopy(schema)
    strict_schema(schema)
    assert schema == before


@pytest.mark.parametrize("status", [500, 502, 503])
async def test_a_server_error_is_unavailable(status: int) -> None:
    generator, _ = stub(api_error("server_error"), status=status)
    with pytest.raises(GeneratorUnavailableError) as caught:
        await generator.generate(MESSAGES)
    assert caught.value.status_code == status


@pytest.mark.parametrize("code", ["rate_limit_exceeded", "insufficient_quota"])
async def test_every_429_is_unavailable(code: str) -> None:
    generator, _ = stub(api_error(code), status=429)
    with pytest.raises(GeneratorUnavailableError, match=code) as caught:
        await generator.generate(MESSAGES)
    assert caught.value.status_code == 429


async def test_an_exhausted_credit_balance_names_itself_apart_from_a_rate_limit() -> None:
    body = {
        "error": {
            "message": "You exceeded your current quota.",
            "type": "insufficient_quota",
            "param": None,
            "code": "credit_balance_exhausted",
        }
    }
    generator, _ = stub(body, status=429)
    with pytest.raises(GeneratorUnavailableError) as caught:
        await generator.generate(MESSAGES)
    assert "code=credit_balance_exhausted" in str(caught.value)
    assert "type=insufficient_quota" in str(caught.value)
    assert "exceeded your current quota" not in str(caught.value)


async def test_a_model_that_forbids_logprobs_is_a_request_error() -> None:
    body = api_error(None, "You are not allowed to request logprobs from this model")
    generator, _ = stub(body, status=403)
    with pytest.raises(GenerationRequestError) as caught:
        await generator.generate(MESSAGES, top_logprobs=2)
    assert caught.value.status_code == 403
    assert "not allowed" not in str(caught.value)


async def test_an_unreachable_api_is_unavailable() -> None:
    generator, _ = stub(raises=httpx.ConnectError("refused"))
    with pytest.raises(GeneratorUnavailableError, match="unreachable"):
        await generator.generate(MESSAGES)


async def test_a_redirect_is_unavailable() -> None:
    generator, _ = stub(status=307, headers={"location": "https://elsewhere.test"})
    with pytest.raises(GeneratorUnavailableError, match="redirected"):
        await generator.generate(MESSAGES)


async def test_a_context_overflow_has_its_own_error() -> None:
    generator, _ = stub(api_error("context_length_exceeded", "too long"), status=400)
    with pytest.raises(ContextOverflowError):
        await generator.generate(MESSAGES)


@pytest.mark.parametrize(
    ("status", "code"), [(400, "invalid_value"), (401, "invalid_api_key"), (404, "model_not_found")]
)
async def test_other_client_errors_are_request_errors(status: int, code: str) -> None:
    generator, _ = stub(api_error(code), status=status)
    with pytest.raises(GenerationRequestError) as caught:
        await generator.generate(MESSAGES)
    assert not isinstance(caught.value, ContextOverflowError)
    assert caught.value.status_code == status


async def test_error_text_never_carries_the_provider_message_or_key() -> None:
    generator, _ = stub(
        api_error("invalid_api_key", f"Incorrect API key provided: {KEY}"), status=401
    )
    with pytest.raises(GenerationRequestError) as caught:
        await generator.generate(MESSAGES)
    assert KEY not in str(caught.value)
    assert "Incorrect API key" not in str(caught.value)
    assert "invalid_api_key" in str(caught.value)


async def test_a_non_json_error_body_still_maps_cleanly() -> None:
    generator, _ = stub(status=400, text="<html>bad gateway</html>")
    with pytest.raises(GenerationRequestError, match="no parseable error body"):
        await generator.generate(MESSAGES)


@pytest.mark.parametrize(
    "body",
    [
        {"choices": []},
        {"choices": [{"message": {}}]},
        {"usage": {}},
        {
            "choices": [{"message": {"content": 3}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        },
    ],
)
async def test_an_unusable_success_body_is_unavailable(body: dict[str, Any]) -> None:
    generator, _ = stub(body)
    with pytest.raises(GeneratorUnavailableError, match="unusable body"):
        await generator.generate(MESSAGES)


async def test_empty_messages_are_refused_before_any_request() -> None:
    generator, seen = stub()
    with pytest.raises(ValueError):
        await generator.generate([])
    assert seen == []


def test_without_a_key_it_cannot_be_built(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "openai_api_key", None)
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        OpenAIGenerator()


async def test_the_factory_builds_the_configured_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "openai_api_key", SecretStr(KEY))
    monkeypatch.setattr(settings, "generation_provider", "openai")
    openai = generators.build_generator(12)
    monkeypatch.setattr(settings, "generation_provider", "ollama")
    ollama = generators.build_generator(12)
    try:
        assert isinstance(openai, OpenAIGenerator)
        assert isinstance(ollama, OllamaGenerator)
        assert openai._client.timeout.read == 12.0
        assert str(openai._client.base_url).rstrip("/") == settings.openai_base_url
        assert openai._client.follow_redirects is False
    finally:
        await openai.aclose()
        await ollama.aclose()


@pytest.mark.skipif(
    os.environ.get("OPENAI_LIVE") != "1",
    reason="spends real money; set OPENAI_LIVE=1 with OPENAI_API_KEY configured",
)
async def test_a_live_openai_answers_a_strict_schema_at_temperature_zero() -> None:
    generator = OpenAIGenerator()
    schema = {"type": "object", "properties": {"city": {"type": "string"}}}
    try:
        result = await generator.generate(
            MESSAGES,
            sampling=SamplingSettings(temperature=0.0, seed=0, max_output_tokens=32),
            response_schema=schema,
        )
    finally:
        await generator.aclose()
    assert "city" in json.loads(result.text)
    assert result.usage.prompt_tokens > 0
