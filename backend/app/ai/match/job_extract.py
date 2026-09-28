from dataclasses import dataclass

from pydantic import ValidationError

from app.ai.generation import (
    GenerationRequestError,
    GenerationResult,
    Generator,
    GeneratorUnavailableError,
    Message,
    SamplingSettings,
)
from app.ai.match.prompts import JOB_EXTRACT_PROMPT, build_job_extract_messages, correction_message
from app.ai.match.schemas import ExtractedJob, JobPosting
from app.ai.output_guard import validate_output

MAX_JOB_TEXT_CHARS = 30_000
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
    except GenerationRequestError:
        raise ExtractionError("internal_error") from None


def _parse(result: GenerationResult) -> tuple[ExtractedJob | None, str]:
    verdict = validate_output(result, protected_prompt=JOB_EXTRACT_PROMPT)
    if verdict.failed_check in _LEAK_CHECKS:
        raise ExtractionError("ai_invalid_output")
    if not verdict.ok:
        return None, f"reply was {verdict.failed_check}"
    try:
        return ExtractedJob.model_validate_json(result.text), ""
    except ValidationError as exc:
        # Paths and error types only: echoing the reply back would feed its content forward.
        problems = (
            f"{'.'.join(str(part) for part in error['loc']) or 'reply'}: {error['type']}"
            for error in exc.errors()[:10]
        )
        return None, "; ".join(problems)


async def extract_job(generator: Generator, text: str) -> Extraction:
    truncated = len(text) > MAX_JOB_TEXT_CHARS
    messages = build_job_extract_messages(text[:MAX_JOB_TEXT_CHARS])

    parsed, problems = _parse(await _generate(generator, messages))
    if parsed is None:
        parsed, _ = _parse(await _generate(generator, [*messages, correction_message(problems)]))
    if parsed is None:
        raise ExtractionError("ai_invalid_output")
    if not parsed.is_job_posting:
        raise ExtractionError("not_a_job_posting")

    posting = JobPosting.model_validate(parsed.model_dump(exclude={"is_job_posting"}))
    return Extraction(posting=posting, input_truncated=truncated)
