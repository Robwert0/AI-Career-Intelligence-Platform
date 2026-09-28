import hashlib
import math
import random
from typing import Any

from redis.exceptions import RedisError

from app.ai.generation import (
    FinishReason,
    GenerationRequestError,
    GenerationResult,
    GeneratorUnavailableError,
    Message,
    SamplingSettings,
    Usage,
)
from app.core.config import settings
from app.core.rate_limiter import Decision, Policy


class FakeEmbedder:
    @property
    def model_name(self) -> str:
        return "fake-embedder"

    @property
    def dimensions(self) -> int:
        return settings.embedding_dim

    def _vector(self, text: str) -> list[float]:
        seed = int.from_bytes(hashlib.sha256(text.encode()).digest()[:8])
        rng = random.Random(seed)
        values = [rng.gauss(0.0, 1.0) for _ in range(self.dimensions)]
        length = math.sqrt(sum(value * value for value in values))
        return [value / length for value in values]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)


class NearEmbedder(FakeEmbedder):
    """Every vector is identical, so cosine similarity is 1.0 and the refusal gate always passes."""

    def _vector(self, text: str) -> list[float]:
        length = math.sqrt(self.dimensions)
        return [1.0 / length] * self.dimensions


class FakeGenerator:
    def __init__(
        self,
        text: str = "a fake answer",
        finish_reason: FinishReason = FinishReason.STOP,
    ) -> None:
        self._text = text
        self._finish_reason = finish_reason
        self.calls: list[list[Message]] = []
        self.sampling: list[SamplingSettings] = []
        self.response_schemas: list[dict[str, Any] | None] = []

    @property
    def model_name(self) -> str:
        return "fake-generator"

    async def generate(
        self,
        messages: list[Message],
        *,
        sampling: SamplingSettings | None = None,
        top_logprobs: int | None = None,
        response_schema: dict[str, Any] | None = None,
    ) -> GenerationResult:
        self.calls.append(messages)
        settings_used = sampling or SamplingSettings()
        self.sampling.append(settings_used)
        self.response_schemas.append(response_schema)
        return GenerationResult(
            text=self._text,
            finish_reason=self._finish_reason,
            model=self.model_name,
            usage=Usage(
                prompt_tokens=sum(len(message.content.split()) for message in messages),
                completion_tokens=len(self._text.split()),
            ),
            latency_ms=0,
            sampling=settings_used,
        )

    async def aclose(self) -> None:
        return None


class UnavailableGenerator:
    @property
    def model_name(self) -> str:
        return "unavailable-generator"

    async def generate(
        self,
        messages: list[Message],
        *,
        sampling: SamplingSettings | None = None,
        top_logprobs: int | None = None,
        response_schema: dict[str, Any] | None = None,
    ) -> GenerationResult:
        raise GeneratorUnavailableError("the fake provider is down")


class RejectingGenerator:
    @property
    def model_name(self) -> str:
        return "rejecting-generator"

    async def generate(
        self,
        messages: list[Message],
        *,
        sampling: SamplingSettings | None = None,
        top_logprobs: int | None = None,
        response_schema: dict[str, Any] | None = None,
    ) -> GenerationResult:
        raise GenerationRequestError("the fake provider rejected the request")


class AllowAllLimiter:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def check(self, policy: Policy, identity: str, *, now: float) -> Decision:
        self.calls.append((policy.name, identity))
        return Decision(allowed=True, remaining=float(policy.capacity), retry_after_seconds=0.0)


class UnavailableLimiter:
    async def check(self, policy: Policy, identity: str, *, now: float) -> Decision:
        raise RedisError("redis is down")


class ScriptedGenerator:
    """Returns one scripted reply per call, in order; the retry path needs distinct answers."""

    def __init__(self, texts: list[str], finish_reasons: list[FinishReason] | None = None) -> None:
        self._texts = list(texts)
        self._finish_reasons = list(finish_reasons or [FinishReason.STOP] * len(texts))
        self.calls: list[list[Message]] = []
        self.response_schemas: list[dict[str, Any] | None] = []
        self.sampling: list[SamplingSettings] = []

    @property
    def model_name(self) -> str:
        return "scripted-generator"

    async def generate(
        self,
        messages: list[Message],
        *,
        sampling: SamplingSettings | None = None,
        top_logprobs: int | None = None,
        response_schema: dict[str, Any] | None = None,
    ) -> GenerationResult:
        index = len(self.calls)
        self.calls.append(messages)
        self.response_schemas.append(response_schema)
        used = sampling or SamplingSettings()
        self.sampling.append(used)
        return GenerationResult(
            text=self._texts[index],
            finish_reason=self._finish_reasons[index],
            model=self.model_name,
            usage=Usage(prompt_tokens=0, completion_tokens=0),
            latency_ms=0,
            sampling=used,
        )

    async def aclose(self) -> None:
        return None


class FakeTaskQueue:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.attempted: list[tuple[str, str]] = []
        self.enqueued: list[tuple[str, str]] = []

    async def enqueue(self, task_name: str, job_id: str) -> None:
        from app.workers.queue import QueueUnavailableError

        self.attempted.append((task_name, job_id))
        if self.fail:
            raise QueueUnavailableError(task_name)
        self.enqueued.append((task_name, job_id))
