from dataclasses import dataclass, replace
from typing import Any

from pydantic import ValidationError

from app.ai.generation import (
    ContextOverflowError,
    GenerationRequestError,
    GenerationResult,
    Generator,
    GeneratorUnavailableError,
    Message,
    SamplingSettings,
)
from app.ai.match.prompts import JOB_EXTRACT_PROMPT, build_job_extract_messages, correction_message
from app.ai.match.schemas import ExtractedJob, JobPosting
from app.ai.output_guard import Verdict, validate_output

MAX_JOB_TEXT_CHARS = 30_000
MAX_JOB_TEXT_BYTES = 60_000
JOB_EXTRACT_SAMPLING = SamplingSettings(temperature=0.0, seed=0, max_output_tokens=2048)
_LEAK_CHECKS = frozenset({"canary", "ngram"})
_SCHEMA = ExtractedJob.model_json_schema()


class ExtractionError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class Extraction:
    posting: JobPosting
    input_truncated: bool


async def _generate(generator: Generator, messages: list[Message]) -> GenerationResult:
    try:
        return await generator.generate(
            messages, sampling=JOB_EXTRACT_SAMPLING, response_schema=_SCHEMA
        )
    except GeneratorUnavailableError:
        raise ExtractionError("ai_unavailable") from None
    except ContextOverflowError:
        raise ExtractionError("input_too_long") from None
    except GenerationRequestError:
        raise ExtractionError("internal_error") from None


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        value = list(value.values())
    if isinstance(value, list):
        return [text for item in value for text in _strings(item)]
    return []


def _checked(result: GenerationResult) -> Verdict:
    verdict = validate_output(result, protected_prompt=JOB_EXTRACT_PROMPT)
    if verdict.failed_check in _LEAK_CHECKS:
        raise ExtractionError("ai_invalid_output")
    return verdict


def _parse(result: GenerationResult) -> tuple[ExtractedJob | None, str]:
    verdict = _checked(result)
    if not verdict.ok:
        return None, f"reply was {verdict.failed_check}"
    try:
        parsed = ExtractedJob.model_validate_json(result.text)
    except ValidationError as exc:
        # Paths and error types only: echoing the reply back would feed its content forward.
        problems = (
            f"{'.'.join(str(part) for part in error['loc']) or 'reply'}: {error['type']}"
            for error in exc.errors()[:10]
        )
        return None, "; ".join(problems)
    # The raw check sees JSON source; \u escapes and item boundaries hide what the user reads.
    _checked(replace(result, text="\n".join(_strings(parsed.model_dump()))))
    return parsed, ""


def _cap(text: str) -> tuple[str, bool]:
    # Characters alone don't bound tokens: an emoji is 4 bytes and several tokens.
    encoded = text[:MAX_JOB_TEXT_CHARS].encode()
    capped = encoded[:MAX_JOB_TEXT_BYTES].decode(errors="ignore")
    return capped, len(capped) < len(text)


async def extract_job(generator: Generator, text: str) -> Extraction:
    capped, truncated = _cap(text)
    messages = build_job_extract_messages(capped)

    parsed, problems = _parse(await _generate(generator, messages))
    if parsed is None:
        parsed, _ = _parse(await _generate(generator, [*messages, correction_message(problems)]))
    if parsed is None:
        raise ExtractionError("ai_invalid_output")
    if not parsed.is_job_posting:
        raise ExtractionError("not_a_job_posting")

    posting = JobPosting.model_validate(parsed.model_dump(exclude={"is_job_posting"}))
    return Extraction(posting=posting, input_truncated=truncated)
