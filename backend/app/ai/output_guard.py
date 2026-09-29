import functools
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


def _ngrams(text: str, size: int) -> frozenset[tuple[str, ...]]:
    words = text.lower().split()
    return frozenset(tuple(words[index : index + size]) for index in range(len(words) - size + 1))


@functools.lru_cache(maxsize=8)
def _prompt_ngrams(prompt: str) -> frozenset[tuple[str, ...]]:
    return _ngrams(prompt, NGRAM_SIZE)


def validate_output(result: GenerationResult, *, protected_prompt: str = INDEXED_PROMPT) -> Verdict:
    if not result.text.strip():
        return Verdict(ok=False, failed_check="empty")
    if result.truncated:
        return Verdict(ok=False, failed_check="truncated")
    if _SQUASHED_CANARY in _squashed(result.text):
        return Verdict(ok=False, failed_check="canary")
    if _ngrams(result.text, NGRAM_SIZE) & _prompt_ngrams(protected_prompt):
        return Verdict(ok=False, failed_check="ngram")

    return Verdict(ok=True)
