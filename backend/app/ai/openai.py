import copy
import time
from typing import Any

import httpx

from app.ai.generation import (
    ContextOverflowError,
    FinishReason,
    GenerationRequestError,
    GenerationResult,
    GeneratorUnavailableError,
    Message,
    SamplingSettings,
    TokenLogprob,
    Usage,
)
from app.core.config import settings

FINISH_REASONS = {"stop": FinishReason.STOP, "length": FinishReason.LENGTH}
_CONTEXT_OVERFLOW = "context_length_exceeded"


def strict_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Strict structured outputs demand every property required and no extra keys."""
    strict = copy.deepcopy(schema)

    def tighten(node: Any) -> None:
        if isinstance(node, dict):
            if isinstance(node.get("properties"), dict):
                node["required"] = list(node["properties"])
                node["additionalProperties"] = False
            for value in node.values():
                tighten(value)
        elif isinstance(node, list):
            for item in node:
                tighten(item)

    tighten(strict)
    return strict


def _sampling(sampling: SamplingSettings) -> dict[str, Any]:
    if sampling.top_k is not None:
        raise GenerationRequestError("OpenAI has no top_k; the sampling would be silently changed")
    knobs: dict[str, Any] = {
        "temperature": sampling.temperature,
        "top_p": sampling.top_p,
        "max_completion_tokens": sampling.max_output_tokens,
    }
    if sampling.seed is not None:
        knobs["seed"] = sampling.seed
    return knobs


def _logprobs(choice: dict[str, Any]) -> tuple[TokenLogprob, ...] | None:
    steps = (choice.get("logprobs") or {}).get("content")
    if steps is None:
        return None
    return tuple(
        TokenLogprob(
            token=step["token"],
            logprob=step["logprob"],
            alternatives=tuple(
                (alternative["token"], alternative["logprob"])
                for alternative in step.get("top_logprobs", ())
            ),
        )
        for step in steps
    )


def _error_fields(response: httpx.Response) -> str:
    # Never the message: a 401 message echoes part of the key.
    try:
        error = response.json().get("error") or {}
    except ValueError, AttributeError:
        return "no parseable error body"
    if not isinstance(error, dict):
        return "no parseable error body"
    return " ".join(f"{field}={error.get(field)}" for field in ("code", "type", "param"))


def _error_code(response: httpx.Response) -> str | None:
    try:
        error = response.json().get("error") or {}
    except ValueError, AttributeError:
        return None
    return error.get("code") if isinstance(error, dict) else None


class OpenAIGenerator:
    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        model: str | None = None,
        timeout_seconds: int | None = None,
        reasoning_effort: str | None = None,
    ) -> None:
        self._model = model or settings.openai_chat_model
        self._reasoning_effort = reasoning_effort or settings.openai_reasoning_effort
        if client is None:
            if settings.openai_api_key is None:
                raise ValueError("OPENAI_API_KEY is required for the openai provider")
            client = httpx.AsyncClient(
                base_url=settings.openai_base_url,
                headers={"Authorization": f"Bearer {settings.openai_api_key.get_secret_value()}"},
                timeout=httpx.Timeout(
                    timeout_seconds or settings.generation_timeout_seconds,
                    connect=settings.generation_connect_timeout_seconds,
                ),
            )
        self._client = client

    @property
    def model_name(self) -> str:
        return f"openai/{self._model}"

    async def aclose(self) -> None:
        await self._client.aclose()

    async def generate(
        self,
        messages: list[Message],
        *,
        sampling: SamplingSettings | None = None,
        top_logprobs: int | None = None,
        response_schema: dict[str, Any] | None = None,
    ) -> GenerationResult:
        if not messages:
            raise ValueError("cannot generate without at least one message")

        sampling = sampling or SamplingSettings()
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            **_sampling(sampling),
        }
        # Without "none" a reasoning model rejects temperature=0 and spends hidden tokens
        # out of max_completion_tokens.
        if self._reasoning_effort is not None:
            payload["reasoning_effort"] = self._reasoning_effort
        if top_logprobs is not None:
            payload["logprobs"] = True
            payload["top_logprobs"] = top_logprobs
        if response_schema is not None:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "reply",
                    "strict": True,
                    "schema": strict_schema(response_schema),
                },
            }

        started = time.perf_counter()
        try:
            response = await self._client.post("/chat/completions", json=payload)
        except httpx.RequestError as exc:
            raise GeneratorUnavailableError(
                f"{self.model_name} is unreachable: {type(exc).__name__}"
            ) from exc
        latency_ms = round((time.perf_counter() - started) * 1000)

        status = response.status_code
        if status >= 500 or status == 429:
            raise GeneratorUnavailableError(
                f"{self.model_name} failed with {status}: {_error_fields(response)}",
                status_code=status,
            )
        if response.is_redirect:
            raise GeneratorUnavailableError(
                f"{self.model_name} redirected; the configured base url is not an API endpoint",
                status_code=status,
            )
        if status == 400 and _error_code(response) == _CONTEXT_OVERFLOW:
            raise ContextOverflowError(
                f"{self.model_name} refused a prompt larger than its context window",
                status_code=status,
            )
        if response.is_error:
            raise GenerationRequestError(
                f"{self.model_name} rejected the request with {status}: {_error_fields(response)}",
                status_code=status,
            )

        try:
            body = response.json()
            choice = body["choices"][0]
            message = choice["message"]
            text = message.get("content")
            if text is None:
                text = message["refusal"]
                finish_reason = FinishReason.OTHER
            else:
                finish_reason = FINISH_REASONS.get(choice.get("finish_reason"), FinishReason.OTHER)
            if not isinstance(text, str):
                raise TypeError(f"content is {type(text).__name__}")
            usage = Usage(body["usage"]["prompt_tokens"], body["usage"]["completion_tokens"])
            logprobs = _logprobs(choice)
        except (ValueError, KeyError, TypeError, IndexError) as exc:
            raise GeneratorUnavailableError(
                f"{self.model_name} answered {status} with an unusable body: {type(exc).__name__}",
                status_code=status,
            ) from exc

        return GenerationResult(
            text=text,
            finish_reason=finish_reason,
            model=self.model_name,
            usage=usage,
            latency_ms=latency_ms,
            sampling=sampling,
            logprobs=logprobs,
        )
