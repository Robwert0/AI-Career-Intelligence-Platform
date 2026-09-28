import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from app.ai.generation import Generator
from app.ai.input_guard import detect_injection_phrases
from app.ai.match.evidence_extract import CvEvidence, extract_cv_evidence, github_evidence
from app.ai.match.schemas import EvidenceItem
from app.ai.match.structured import ExtractionError
from app.core.config import settings
from app.integrations.doc_parse import DocumentKind, ParsedDocument, parse_pasted
from app.integrations.doc_sandbox import parse_isolated
from app.integrations.errors import DocumentError, DocumentFailure, GitHubError
from app.integrations.github import (
    GitHubCache,
    GitHubFetcher,
    load_github,
    parse_github_profile_url,
)

logger = logging.getLogger(__name__)

DocumentParser = Callable[[bytes], Awaitable[ParsedDocument]]
# Amendment 5: a CV read shares ExtractionError with job intake, but "ai_invalid_output" and
# "input_too_long" carry job-posting wording and a "Try again" recovery — wrong for a source the
# user can simply continue without. Every other code (ai_unavailable, internal_error, not_a_cv)
# already reads fine unprefixed and keeps its own catalogue entry.
_CV_SPECIFIC_CODES = {
    "ai_invalid_output": "cv_ai_invalid_output",
    "input_too_long": "cv_input_too_long",
}


class SourceError(Exception):
    def __init__(
        self, code: str, *, reset_at: int | None = None, dropped: int | None = None
    ) -> None:
        super().__init__(code)
        self.code = code
        self.reset_at = reset_at
        # How many extracted items failed grounding, when known: lets the caller (slice 4) add a
        # "many items were dropped" limitation line even though the source itself failed.
        self.dropped = dropped


@dataclass(frozen=True, slots=True)
class CvReading:
    evidence: CvEvidence
    document_kind: DocumentKind
    pages: int | None
    truncated: bool


@dataclass(frozen=True, slots=True)
class GitHubReading:
    items: tuple[EvidenceItem, ...]
    username: str
    public_repos: int
    candidate_repos: int
    inspected_repos: int
    readmes_found: int


async def _document(file: bytes | None, text: str | None, parse: DocumentParser) -> ParsedDocument:
    try:
        if file is not None:
            if len(file) > settings.max_upload_bytes:
                raise DocumentError(DocumentFailure.FILE_TOO_LARGE)
            return await parse(file)
        assert text is not None
        return parse_pasted(text)
    except DocumentError as exc:
        raise SourceError(exc.failure.value) from None


async def read_cv(
    *,
    file: bytes | None = None,
    text: str | None = None,
    generator: Generator,
    parse: DocumentParser = parse_isolated,
) -> CvReading:
    if (file is None) == (text is None):
        raise ValueError("provide exactly one of file or text")
    document = await _document(file, text, parse)
    try:
        evidence = await extract_cv_evidence(generator, document.text)
    except ExtractionError as exc:
        raise SourceError(_CV_SPECIFIC_CODES.get(exc.code, exc.code)) from None
    if not evidence.items:
        raise SourceError("cv_no_evidence", dropped=evidence.dropped)
    logger.info(
        "cv read kind=%s pages=%s chars=%d items=%d dropped=%d",
        document.kind,
        document.pages,
        len(document.text),
        len(evidence.items),
        evidence.dropped,
    )
    return CvReading(
        evidence=evidence,
        document_kind=document.kind,
        pages=document.pages,
        truncated=document.truncated or evidence.input_truncated,
    )


async def read_github(
    profile_url: str, *, fetcher: GitHubFetcher, cache: GitHubCache
) -> GitHubReading:
    try:
        username = parse_github_profile_url(profile_url)
        snapshot = await load_github(username, fetcher=fetcher, cache=cache)
    except GitHubError as exc:
        raise SourceError(exc.failure.value, reset_at=exc.reset_at) from None
    items = github_evidence(snapshot)
    flagged = detect_injection_phrases(" ".join(item.text for item in items))
    if flagged:
        logger.warning("github injection phrasing detected patterns=%s", ",".join(flagged))
    logger.info(
        "github read repos=%d readmes=%d items=%d",
        len(snapshot.repos),
        snapshot.readmes_found,
        len(items),
    )
    return GitHubReading(
        items=items,
        username=snapshot.profile.login,
        public_repos=snapshot.profile.public_repos,
        candidate_repos=snapshot.candidate_repos,
        inspected_repos=len(snapshot.repos),
        readmes_found=snapshot.readmes_found,
    )
