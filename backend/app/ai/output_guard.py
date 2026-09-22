import re
from dataclasses import dataclass

from app.ai.generation import GenerationResult
from app.ai.prompts import CANARY, INDEXED_PROMPT

NGRAM_SIZE = 8

_NON_ALPHANUMERIC = re.compile(r"[^a-z0-9]")


@dataclass(frozen=True, slots=True)
class Verdict:
    ok: bool
    failed_check: str | None = None


def _squashed(text: str) -> str:
    return _NON_ALPHANUMERIC.sub("", text.lower())


_SQUASHED_CANARY = _squashed(CANARY)


def _ngrams(text: str, size: int) -> set[tuple[str, ...]]:
    words = text.lower().split()
    return {tuple(words[index : index + size]) for index in range(len(words) - size + 1)}


_INDEXED_NGRAMS = _ngrams(INDEXED_PROMPT, NGRAM_SIZE)


def validate_output(result: GenerationResult) -> Verdict:
    if not result.text.strip():
        return Verdict(ok=False, failed_check="empty")
    if result.truncated:
        return Verdict(ok=False, failed_check="truncated")
    if _SQUASHED_CANARY in _squashed(result.text):
        return Verdict(ok=False, failed_check="canary")
    if _ngrams(result.text, NGRAM_SIZE) & _INDEXED_NGRAMS:
        return Verdict(ok=False, failed_check="ngram")

    return Verdict(ok=True)
