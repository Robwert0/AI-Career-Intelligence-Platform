from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

Role = StrEnum("Role", ("SYSTEM", "USER", "ASSISTANT"))
FinishReason = StrEnum("FinishReason", ("STOP", "LENGTH", "OTHER"))


class SamplingSettings(BaseModel):
    model_config = ConfigDict(frozen=True)

    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    top_p: float = Field(default=1.0, gt=0.0, le=1.0)
    top_k: int | None = Field(default=None, ge=1)
    seed: int | None = None
    max_output_tokens: int = Field(default=512, ge=1)


@dataclass(frozen=True, slots=True)
class Message:
    role: Role
    content: str


@dataclass(frozen=True, slots=True)
class Usage:
    prompt_tokens: int
    completion_tokens: int


@dataclass(frozen=True, slots=True)
class TokenLogprob:
    token: str
    logprob: float
    alternatives: tuple[tuple[str, float], ...] = ()


@dataclass(frozen=True, slots=True)
class GenerationResult:
    text: str
    finish_reason: FinishReason
    model: str
    usage: Usage
    latency_ms: int
    sampling: SamplingSettings
    thinking: str | None = None
    logprobs: tuple[TokenLogprob, ...] | None = None

    @property
    def truncated(self) -> bool:
        return self.finish_reason is FinishReason.LENGTH


class GeneratorUnavailableError(Exception):
    """Provider unreachable or failing; the same request may succeed on a later retry."""


class GenerationRequestError(Exception):
    """Provider rejected the request itself; retrying it unchanged will fail identically."""


class Generator(Protocol):
    @property
    def model_name(self) -> str: ...

    async def generate(
        self,
        messages: list[Message],
        *,
        sampling: SamplingSettings | None = None,
        top_logprobs: int | None = None,
    ) -> GenerationResult: ...
