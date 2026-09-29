import logging
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from app.ai.generation import Generator
from app.ai.input_guard import detect_injection_phrases
from app.ai.match.job_extract import ExtractionError, extract_job
from app.integrations.errors import FetchError
from app.integrations.html_text import extract_page, job_text, page_failure, plain_page
from app.integrations.safe_fetch import FetchResult
from app.schemas.match import JobIntakeRequest

logger = logging.getLogger(__name__)

StageCallback = Callable[[str], Awaitable[None]]


class Fetcher(Protocol):
    async def fetch(self, raw_url: str) -> FetchResult: ...


class IntakeError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


async def _read_url(fetcher: Fetcher, url: str) -> tuple[str, dict[str, Any]]:
    try:
        fetched = await fetcher.fetch(url)
    except FetchError as exc:
        raise IntakeError(exc.failure.value) from None
    page = (
        extract_page(fetched.text)
        if fetched.content_type == "text/html"
        else (plain_page(fetched.text))
    )
    failure = page_failure(page)
    if failure is not None:
        raise IntakeError(failure.value)
    return job_text(page), {"kind": "url", "url": fetched.url}


async def run_job_intake(
    intake: JobIntakeRequest,
    *,
    fetcher: Fetcher,
    generator: Generator,
    on_stage: StageCallback,
) -> dict[str, Any]:
    if intake.url is not None:
        text, source = await _read_url(fetcher, intake.url)
    else:
        assert intake.text is not None
        text, source = intake.text, {"kind": "text"}

    flagged = detect_injection_phrases(text)
    if flagged:
        logger.warning("job intake injection phrasing detected patterns=%s", ",".join(flagged))

    await on_stage("extracting")
    try:
        extraction = await extract_job(generator, text)
    except ExtractionError as exc:
        raise IntakeError(exc.code) from None

    return {
        "posting": extraction.posting.model_dump(mode="json"),
        "source": source,
        "input_truncated": extraction.input_truncated,
    }
