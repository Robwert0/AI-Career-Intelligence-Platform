import hashlib
import math
import random

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

    @property
    def model_name(self) -> str:
        return "fake-generator"

    async def generate(
        self,
        messages: list[Message],
        *,
        sampling: SamplingSettings | None = None,
        top_logprobs: int | None = None,
    ) -> GenerationResult:
        self.calls.append(messages)
        settings_used = sampling or SamplingSettings()
        self.sampling.append(settings_used)
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
