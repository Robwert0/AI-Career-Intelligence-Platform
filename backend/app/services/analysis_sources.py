import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict

from app.ai.match.schemas import EvidenceItem
from app.schemas.match import AnalysisInput, SourceName
from app.services.candidate_evidence import CvReading, GitHubReading, SourceError

logger = logging.getLogger(__name__)

SourceState = Literal["pending", "read", "failed", "not_provided", "skipped"]
CV_BLOBS = ("cv_file", "cv_text")

StageCallback = Callable[[str], Awaitable[None]]
BlobTaker = Callable[[str], Awaitable[bytes | None]]
GitHubReader = Callable[[str], Awaitable[GitHubReading]]
Checkpoint = Callable[["SourcesState"], Awaitable[None]]


class CvReader(Protocol):
    async def __call__(
        self, *, file: bytes | None = None, text: str | None = None
    ) -> CvReading: ...


class CvSource(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: SourceState
    error_code: str | None = None
    items: tuple[EvidenceItem, ...] = ()
    truncated: bool = False
    # Extracted items that failed grounding and were left out.
    dropped: int = 0


class GitHubSource(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: SourceState
    url: str | None = None
    error_code: str | None = None
    reset_at: int | None = None
    items: tuple[EvidenceItem, ...] = ()
    inspected_repos: int = 0
    public_non_fork_repos: int = 0
    readmes_found: int = 0


class SourcesState(BaseModel):
    """Checkpointed between runs, so a continue or retry never re-reads a finished source."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    cv: CvSource
    github: GitHubSource


@dataclass(frozen=True, slots=True)
class Ready:
    pass


@dataclass(frozen=True, slots=True)
class Pause:
    source: SourceName
    code: str
    reset_at: int | None


@dataclass(frozen=True, slots=True)
class Fail:
    code: str


def initial_sources(request: AnalysisInput) -> SourcesState:
    return SourcesState(
        cv=CvSource(status="pending" if request.cv_provided else "not_provided"),
        github=GitHubSource(
            status="pending" if request.github_url else "not_provided", url=request.github_url
        ),
    )


def apply_decision(state: SourcesState, *, source: str, resume: str) -> SourcesState:
    """continue skips the failed source; retry reads it again. Anything else changes nothing."""
    if resume not in ("continue", "retry"):
        return state
    skip = resume == "continue"
    if source == "cv" and state.cv.status == "failed":
        cv = state.cv.model_copy(
            update={"status": "skipped"} if skip else {"status": "pending", "error_code": None}
        )
        return state.model_copy(update={"cv": cv})
    if source == "github" and state.github.status == "failed":
        github = state.github.model_copy(
            update={"status": "skipped"}
            if skip
            else {"status": "pending", "error_code": None, "reset_at": None}
        )
        return state.model_copy(update={"github": github})
    return state


def _unexpected(source: str, exc: Exception, fatal: tuple[type[BaseException], ...]) -> str:
    if isinstance(exc, fatal):
        raise exc
    # Type only: a parser or client message can quote the CV or a README.
    logger.warning("source failed source=%s error_type=%s", source, type(exc).__name__)
    return "internal_error"


async def _read_cv(
    take_cv: BlobTaker, read_cv: CvReader, fatal: tuple[type[BaseException], ...]
) -> CvSource:
    # GETDEL before parsing: the raw CV is gone from Redis whatever the parse does next.
    file = await take_cv(CV_BLOBS[0])
    text = None if file is not None else await take_cv(CV_BLOBS[1])
    if file is None and text is None:
        return CvSource(status="failed", error_code="input_expired")
    try:
        reading = await read_cv(
            file=file, text=text.decode("utf-8", errors="replace") if text is not None else None
        )
    except SourceError as exc:
        return CvSource(status="failed", error_code=exc.code, dropped=exc.dropped or 0)
    except Exception as exc:
        return CvSource(status="failed", error_code=_unexpected("cv", exc, fatal))
    return CvSource(
        status="read",
        items=reading.evidence.items,
        truncated=reading.truncated,
        dropped=reading.evidence.dropped,
    )


async def _read_github(
    source: GitHubSource, read_github: GitHubReader, fatal: tuple[type[BaseException], ...]
) -> GitHubSource:
    assert source.url is not None
    try:
        reading = await read_github(source.url)
    except SourceError as exc:
        return GitHubSource(
            status="failed", url=source.url, error_code=exc.code, reset_at=exc.reset_at
        )
    except Exception as exc:
        return GitHubSource(
            status="failed", url=source.url, error_code=_unexpected("github", exc, fatal)
        )
    return GitHubSource(
        status="read",
        url=source.url,
        items=reading.items,
        inspected_repos=reading.inspected_repos,
        public_non_fork_repos=reading.candidate_repos,
        readmes_found=reading.readmes_found,
    )


async def read_sources(
    state: SourcesState,
    *,
    take_cv: BlobTaker,
    read_cv: CvReader,
    read_github: GitHubReader,
    on_stage: StageCallback,
    checkpoint: Checkpoint | None = None,
    fatal: tuple[type[BaseException], ...] = (),
) -> SourcesState:
    """`fatal` exceptions (the worker's time limit) propagate; any other failure fails only its
    own source. Each finished read is checkpointed, so a crash later never loses it."""
    if state.cv.status == "pending":
        await on_stage("reading_cv")
        state = state.model_copy(update={"cv": await _read_cv(take_cv, read_cv, fatal)})
        if checkpoint is not None:
            await checkpoint(state)
    if state.github.status == "pending":
        await on_stage("reading_github")
        github = await _read_github(state.github, read_github, fatal)
        state = state.model_copy(update={"github": github})
        if checkpoint is not None:
            await checkpoint(state)
    return state


def decide(state: SourcesState) -> Ready | Pause | Fail:
    """Pause only when another source produced evidence; sources are never dropped silently."""
    named: tuple[tuple[SourceName, CvSource | GitHubSource], ...] = (
        ("cv", state.cv),
        ("github", state.github),
    )
    failed = [(name, source) for name, source in named if source.status == "failed"]
    if not failed:
        return Ready()
    name, source = failed[0]
    code = source.error_code or "internal_error"
    if any(s.status == "read" and s.items for s in (state.cv, state.github)):
        reset_at = source.reset_at if isinstance(source, GitHubSource) else None
        return Pause(source=name, code=code, reset_at=reset_at)
    return Fail(code=code)
