import pytest

from app.ai.generation import FinishReason, GenerationResult, SamplingSettings, Usage
from app.ai.output_guard import NGRAM_SIZE, validate_output
from app.ai.prompts import CANARY, INDEXED_PROMPT, REFUSAL_TEXT


def generated(text: str, finish_reason: FinishReason = FinishReason.STOP) -> GenerationResult:
    return GenerationResult(
        text=text,
        finish_reason=finish_reason,
        model="fake",
        usage=Usage(prompt_tokens=1, completion_tokens=1),
        latency_ms=0,
        sampling=SamplingSettings(),
    )


def test_a_normal_answer_passes() -> None:
    verdict = validate_output(generated("He worked with FastAPI for four years."))

    assert verdict.ok
    assert verdict.failed_check is None


@pytest.mark.parametrize("text", ["", "   ", "\n\t "])
def test_empty_text_fails(text: str) -> None:
    verdict = validate_output(generated(text))

    assert not verdict.ok
    assert verdict.failed_check == "empty"


def test_truncated_output_fails() -> None:
    verdict = validate_output(generated("He worked with", FinishReason.LENGTH))

    assert not verdict.ok
    assert verdict.failed_check == "truncated"


def test_an_empty_truncated_response_is_reported_as_empty() -> None:
    verdict = validate_output(generated("", FinishReason.LENGTH))

    assert verdict.failed_check == "empty"


def test_a_leaked_canary_fails() -> None:
    verdict = validate_output(generated(f"My reference is {CANARY}."))

    assert not verdict.ok
    assert verdict.failed_check == "canary"


def test_a_verbatim_span_of_the_system_prompt_fails() -> None:
    leaked = " ".join(INDEXED_PROMPT.split()[:20])

    verdict = validate_output(generated(leaked))

    assert not verdict.ok
    assert verdict.failed_check == "ngram"


def test_a_span_shorter_than_the_ngram_window_is_not_flagged() -> None:
    short = " ".join(INDEXED_PROMPT.split()[: NGRAM_SIZE - 1])

    assert validate_output(generated(short)).ok


def test_a_legitimate_refusal_passes() -> None:
    assert validate_output(generated(REFUSAL_TEXT)).ok


def test_an_answer_quoting_ordinary_cv_language_passes() -> None:
    answer = (
        "He answers to a senior engineer and has used only Python and Go in his most recent "
        "role, which he describes in plain terms."
    )

    assert validate_output(generated(answer)).ok
