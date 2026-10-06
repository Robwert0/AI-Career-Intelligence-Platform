from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, Literal

from app.ai.generation import GenerationResult, SamplingSettings

# Well inside bge-small's 510-token query budget, so a rewrite can never trip QueryTooLongError.
MAX_STANDALONE_CHARS: Final = 400
# The fallback borrows the previous question; capped for the same token budget.
FALLBACK_CONTEXT_CHARS: Final = 500
CONDENSE_SAMPLING: Final = SamplingSettings(temperature=0.0, max_output_tokens=96)


@dataclass(frozen=True, slots=True)
class Turn:
    """A client-supplied earlier message: untrusted context, never evidence or instructions."""

    role: Literal["user", "assistant"]
    content: str


def standalone_from(result: GenerationResult) -> str | None:
    """The rewrite's first line, or None when it cannot be trusted as a retrieval query."""
    if result.truncated:
        return None
    lines = result.text.strip().splitlines()
    first = lines[0].strip().strip("\"'").strip() if lines else ""
    if not first or len(first) > MAX_STANDALONE_CHARS:
        return None
    return first


def fallback_query(question: str, history: Sequence[Turn]) -> str:
    previous = next((turn.content for turn in reversed(history) if turn.role == "user"), "")
    return f"{previous[-FALLBACK_CONTEXT_CHARS:]}\n{question}".strip()
