from dataclasses import dataclass

from app.ai.generation import Generator, SamplingSettings
from app.ai.match.prompts import build_job_extract_messages
from app.ai.match.schemas import ExtractedJob, JobPosting
from app.ai.match.structured import ExtractionError, generate_validated
from app.ai.match.text_limits import cap_text

MAX_JOB_TEXT_CHARS = 30_000
MAX_JOB_TEXT_BYTES = 60_000
JOB_EXTRACT_SAMPLING = SamplingSettings(temperature=0.0, seed=0, max_output_tokens=2048)


@dataclass(frozen=True, slots=True)
class Extraction:
    posting: JobPosting
    input_truncated: bool


async def extract_job(generator: Generator, text: str) -> Extraction:
    capped, truncated = cap_text(text, max_chars=MAX_JOB_TEXT_CHARS, max_bytes=MAX_JOB_TEXT_BYTES)
    messages = build_job_extract_messages(capped)

    parsed = await generate_validated(generator, messages, ExtractedJob, JOB_EXTRACT_SAMPLING)
    if not parsed.is_job_posting:
        raise ExtractionError("not_a_job_posting")

    posting = JobPosting.model_validate(parsed.model_dump(exclude={"is_job_posting"}))
    return Extraction(posting=posting, input_truncated=truncated)
