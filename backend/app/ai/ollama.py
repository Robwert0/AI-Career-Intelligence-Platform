import time
from typing import Any

import httpx

from app.ai.generation import (
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


def _finish_reason(done_reason: str | None) -> FinishReason:
    return FINISH_REASONS.get(done_reason or "", FinishReason.OTHER)


def _options(sampling: SamplingSettings) -> dict[str, Any]:
    options: dict[str, Any] = {
        "temperature": sampling.temperature,
        "top_p": sampling.top_p,
        "num_predict": sampling.max_output_tokens,
    }
    if sampling.top_k is not None:
        options["top_k"] = sampling.top_k
    if sampling.seed is not None:
        options["seed"] = sampling.seed
    return options


def _logprobs(steps: list[dict[str, Any]] | None) -> tuple[TokenLogprob, ...] | None:
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


class OllamaGenerator:
    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        model: str | None = None,
    ) -> None:
        self._model = model or settings.generation_model
        self._client = client or httpx.AsyncClient(
            base_url=settings.ollama_base_url,
            timeout=httpx.Timeout(
                settings.generation_timeout_seconds,
                connect=settings.generation_connect_timeout_seconds,
            ),
        )

    @property
    def model_name(self) -> str:
        return f"ollama/{self._model}"

    async def aclose(self) -> None:
        await self._client.aclose()

    async def generate(
        self,
        messages: list[Message],
        *,
        sampling: SamplingSettings | None = None,
        top_logprobs: int | None = None,
    ) -> GenerationResult:
        if not messages:
            raise ValueError("cannot generate without at least one message")

        sampling = sampling or SamplingSettings()
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": False,
            "think": False,
            "options": _options(sampling),
        }
        if top_logprobs is not None:
            payload["logprobs"] = True
            payload["top_logprobs"] = top_logprobs

        started = time.perf_counter()
        try:
            response = await self._client.post("/api/chat", json=payload)
        except httpx.RequestError as exc:
            raise GeneratorUnavailableError(f"{self.model_name} is unreachable: {exc}") from exc
        latency_ms = round((time.perf_counter() - started) * 1000)

        if response.status_code >= 500:
            raise GeneratorUnavailableError(
                f"{self.model_name} failed with {response.status_code}: {response.text}"
            )
        if response.is_error:
            raise GenerationRequestError(
                f"{self.model_name} rejected the request "
                f"with {response.status_code}: {response.text}"
            )

        body = response.json()
        message = body["message"]

        return GenerationResult(
            text=message["content"],
            finish_reason=_finish_reason(body.get("done_reason")),
            model=self.model_name,
            usage=Usage(
                body["prompt_eval_count"],
                body["eval_count"],
            ),
            latency_ms=latency_ms,
            sampling=sampling,
            thinking=message.get("thinking"),
            logprobs=_logprobs(body.get("logprobs")),
        )
