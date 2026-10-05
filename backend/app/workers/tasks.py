import asyncio
import contextlib
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, Protocol

from celery.exceptions import SoftTimeLimitExceeded

from app.ai.embeddings import BgeEmbedder
from app.ai.generation import Generator
from app.ai.match.structured import ExtractionError
from app.ai.ollama import OllamaGenerator
from app.core.config import settings
from app.core.db import SessionLocal, engine
from app.core.job_store import (
    TERMINAL,
    JobRecord,
    JobStateError,
    JobStatus,
    JobStore,
    queue_is_stale,
)
from app.core.redis import create_redis
from app.core.retention_marker import RetentionMarker
from app.integrations.github import GitHubCache, GitHubClient
from app.integrations.safe_fetch import SafeFetcher
from app.repositories import UserRepository
from app.schemas.match import AnalysisInput, JobIntakeRequest
from app.services.analysis_service import analyse
from app.services.analysis_sources import (
    CV_BLOBS,
    Fail,
    Pause,
    SourcesState,
    apply_decision,
    decide,
    initial_sources,
    read_sources,
)
from app.services.candidate_evidence import CvReading, GitHubReading, read_cv, read_github
from app.services.job_intake_service import IntakeError, run_job_intake
from app.services.retention_service import RetentionService
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

JobHandler = Callable[[JobStore, JobRecord], Awaitable[dict[str, Any]]]


class JobError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class NeedsDecision(Exception):
    """The handler stops, and the job waits for the user to continue or retry."""

    def __init__(self, source: str, code: str, *, reset_at: int | None = None) -> None:
        super().__init__(code)
        self.source = source
        self.code = code
        self.reset_at = reset_at


Outcome = Literal["done", "paused", "lost", "failed"]


async def fail_job(store: JobStore, job_id: str, error_code: str) -> None:
    # Already finished: the first outcome stands.
    with contextlib.suppress(JobStateError):
        await store.mark_failed(job_id, error_code=error_code, now=time.time())


async def _run_handler(
    store: JobStore, record: JobRecord, handler: JobHandler
) -> tuple[Outcome, str | None, str | None]:
    # Returns (outcome, error_code, error_type). Every store call stays outside the except
    # blocks: a store failure raised inside one would chain the handler's exception, whose
    # message can carry CV text, into Celery's logged traceback.
    pause: NeedsDecision | None = None
    result: dict[str, Any] = {}
    try:
        result = await handler(store, record)
    except NeedsDecision as exc:
        pause = exc
    except JobError as exc:
        return "failed", exc.code, None
    except SoftTimeLimitExceeded:
        return "failed", "timeout", None
    except Exception as exc:
        return "failed", "internal_error", type(exc).__name__

    try:
        with contextlib.suppress(JobStateError):
            if pause is not None:
                await store.mark_needs_decision(
                    record.id,
                    failed_source=pause.source,
                    error_code=pause.code,
                    reset_at=pause.reset_at,
                    now=time.time(),
                )
                return "paused", None, None
            if await store.mark_done(record.id, result=result, now=time.time()) is None:
                return "lost", None, None
    except Exception as exc:
        return "failed", "internal_error", type(exc).__name__
    return "done", None, None


async def execute_job(
    store: JobStore, job_id: str, handler: JobHandler, *, stage: str | None
) -> None:
    record = await store.load(job_id)
    if record is None:
        logger.info("job skipped job_id=%s reason=expired", job_id)
        return
    if record.status in TERMINAL or record.status is JobStatus.NEEDS_DECISION:
        logger.info("job skipped job_id=%s reason=redelivered status=%s", job_id, record.status)
        return
    if record.status is JobStatus.RUNNING:
        # Only a crashed or killed worker leaves a job running; re-running the input that
        # crashed it would loop until the record expires and block every other job meanwhile.
        await fail_job(store, job_id, "worker_lost")
        logger.warning("job failed job_id=%s error_code=worker_lost", job_id)
        return
    if queue_is_stale(record, now=time.time(), limit_seconds=settings.job_queue_stale_seconds):
        # The API already shows this job as queue_unavailable and has freed its slot.
        await fail_job(store, job_id, "queue_unavailable")
        logger.warning("job failed job_id=%s error_code=queue_unavailable", job_id)
        return

    running = await store.mark_running(job_id, stage=stage, now=time.time())
    if running is None:
        return

    started = time.monotonic()
    outcome, error_code, error_type = await _run_handler(store, running, handler)
    if outcome == "failed":
        await fail_job(store, job_id, error_code or "internal_error")
        logger.warning(
            "job failed job_id=%s error_code=%s error_type=%s", job_id, error_code, error_type
        )
        return
    if outcome == "lost":
        # The record expired mid-run; the xx write refused to recreate it, so the result is gone.
        logger.warning("job lost job_id=%s reason=expired", job_id)
        return

    logger.info(
        "job %s job_id=%s kind=%s duration_ms=%d",
        outcome,
        job_id,
        running.kind,
        (time.monotonic() - started) * 1000,
    )


async def _with_store(work: Callable[[JobStore], Awaitable[None]]) -> None:
    # A fresh client per task: a client bound to a previous asyncio.run loop fails on reuse.
    redis = create_redis()
    try:
        await work(JobStore(redis, ttl_seconds=settings.job_ttl_seconds))
    finally:
        await redis.aclose()


def run_job(job_id: str, handler: JobHandler, *, stage: str | None) -> None:
    timed_out = False
    try:
        asyncio.run(_with_store(lambda store: execute_job(store, job_id, handler, stage=stage)))
    except SoftTimeLimitExceeded:
        # The signal can land outside the handler, e.g. inside the event loop itself.
        timed_out = True
    if timed_out:
        asyncio.run(_with_store(lambda store: fail_job(store, job_id, "timeout")))
        logger.warning("job failed job_id=%s error_code=timeout", job_id)


async def _pong(store: JobStore, record: JobRecord) -> dict[str, Any]:
    return {"pong": True}


@celery_app.task(name="jobs.ping")
def ping(job_id: str) -> None:
    run_job(job_id, _pong, stage="ping")


async def _extract_job(store: JobStore, record: JobRecord) -> dict[str, Any]:
    raw = await store.take_blob(record.id, "input")
    if raw is None:
        raise JobError("input_expired")
    intake = JobIntakeRequest.model_validate_json(raw)
    shown: str | None = None

    async def on_stage(stage: str) -> None:
        nonlocal shown
        if stage != shown:
            await store.mark_running(record.id, stage=stage, now=time.time())
            shown = stage

    # Pasted text has nothing to read, so it must never be shown as "reading".
    await on_stage("reading" if intake.url is not None else "extracting")

    generator = OllamaGenerator(timeout_seconds=settings.job_extract_generation_timeout_seconds)
    try:
        return await run_job_intake(
            intake, fetcher=SafeFetcher(), generator=generator, on_stage=on_stage
        )
    except IntakeError as exc:
        raise JobError(exc.code) from None
    finally:
        await generator.aclose()


@celery_app.task(name="jobs.extract_job")
def extract_job_task(job_id: str) -> None:
    # The stage depends on the input kind, which only the handler learns from the blob.
    run_job(job_id, _extract_job, stage=None)


ANALYSIS_BLOBS = ("analysis_input", "sources", "github_url", *CV_BLOBS)


class ClosableGenerator(Generator, Protocol):
    async def aclose(self) -> None: ...


@dataclass(frozen=True, slots=True)
class AnalysisGenerators:
    evidence: ClosableGenerator
    assess: ClosableGenerator
    recommend: ClosableGenerator

    async def aclose(self) -> None:
        for generator in (self.evidence, self.assess, self.recommend):
            await generator.aclose()


def build_analysis_generators() -> AnalysisGenerators:
    # One client per stage: each timeout is part of the budget the settings validator checks.
    return AnalysisGenerators(
        evidence=OllamaGenerator(
            timeout_seconds=settings.evidence_extract_generation_timeout_seconds
        ),
        assess=OllamaGenerator(timeout_seconds=settings.match_assess_generation_timeout_seconds),
        recommend=OllamaGenerator(
            timeout_seconds=settings.match_recommend_generation_timeout_seconds
        ),
    )


def _github_token() -> str | None:
    return settings.github_token.get_secret_value() if settings.github_token else None


def _sources(
    record: JobRecord, request: AnalysisInput, saved: bytes | None, corrected_url: bytes | None
) -> SourcesState:
    state = SourcesState.model_validate_json(saved) if saved else initial_sources(request)
    if record.resume is not None and record.failed_source is not None:
        state = apply_decision(state, source=record.failed_source, resume=record.resume)
    if corrected_url is not None and state.github.status == "pending":
        github = state.github.model_copy(update={"url": corrected_url.decode()})
        state = state.model_copy(update={"github": github})
    return state


_ANALYSIS_CODES = {
    "ai_invalid_output": "analysis_ai_invalid_output",
    "input_too_long": "analysis_input_too_long",
}


def analysis_failure_code(code: str) -> str:
    # The shared loop's codes are worded for job intake; an analysis needs its own copy.
    return _ANALYSIS_CODES.get(code, code)


async def _run_analysis(store: JobStore, record: JobRecord) -> dict[str, Any]:
    raw = await store.read_blob(record.id, "analysis_input")
    if raw is None:
        raise JobError("input_expired")
    request = AnalysisInput.model_validate_json(raw)
    state = _sources(
        record,
        request,
        await store.read_blob(record.id, "sources"),
        await store.take_blob(record.id, "github_url"),
    )

    async def on_stage(stage: str) -> None:
        await store.mark_running(record.id, stage=stage, now=time.time())

    async def take_cv(name: str) -> bytes | None:
        return await store.take_blob(record.id, name)

    async def checkpoint(sources: SourcesState) -> None:
        await store.attach_blob(record.id, "sources", sources.model_dump_json().encode())

    generators = build_analysis_generators()
    redis = create_redis()
    github = GitHubClient(token=_github_token())
    cache = GitHubCache(redis, ttl_seconds=settings.github_cache_ttl_seconds)

    async def read_cv_source(*, file: bytes | None = None, text: str | None = None) -> CvReading:
        return await read_cv(file=file, text=text, generator=generators.evidence)

    async def read_github_source(url: str) -> GitHubReading:
        return await read_github(url, fetcher=github, cache=cache)

    try:
        state = await read_sources(
            state,
            take_cv=take_cv,
            read_cv=read_cv_source,
            read_github=read_github_source,
            on_stage=on_stage,
            checkpoint=checkpoint,
            fatal=(SoftTimeLimitExceeded,),
        )
        verdict = decide(state)
        if isinstance(verdict, Pause):
            raise NeedsDecision(verdict.source, verdict.code, reset_at=verdict.reset_at)
        if isinstance(verdict, Fail):
            raise JobError(verdict.code)
        outcome = await analyse(
            request.posting,
            state,
            embedder=BgeEmbedder(),
            assess_generator=generators.assess,
            recommend_generator=generators.recommend,
            on_stage=on_stage,
            top_k=settings.match_preselect_top_k,
            min_similarity=settings.match_preselect_thresholds,
        )
    except ExtractionError as exc:
        raise JobError(analysis_failure_code(exc.code)) from None
    finally:
        await generators.aclose()
        await redis.aclose()

    metrics = outcome.metrics
    logger.info(
        "analysis finished job_id=%s requirements=%d evidence=%d refused=%s cited=%d "
        "dropped_citations=%d downgraded=%d dropped_advice=%d advice_error=%s",
        record.id,
        metrics.requirements,
        metrics.evidence_items,
        metrics.refused,
        metrics.cited,
        metrics.dropped_citations,
        metrics.downgraded,
        metrics.dropped_advice,
        metrics.advice_error,
    )
    return {"report": outcome.report.model_dump(mode="json")}


async def forget_finished_inputs(store: JobStore, job_id: str) -> None:
    """Deletes the CV and evidence blobs once no continue or retry can need them."""
    record = await store.load(job_id)
    if record is None or record.status in TERMINAL:
        await store.delete_blobs(job_id, *ANALYSIS_BLOBS)


@celery_app.task(
    name="jobs.run_analysis",
    soft_time_limit=settings.match_analysis_soft_time_limit_seconds,
    time_limit=settings.match_analysis_hard_time_limit_seconds,
)
def run_analysis_task(analysis_id: str) -> None:
    run_job(analysis_id, _run_analysis, stage=None)
    asyncio.run(_with_store(lambda store: forget_finished_inputs(store, analysis_id)))


async def _purge_inactive_accounts() -> None:
    now = datetime.now(UTC)
    try:
        async with SessionLocal() as session:
            purged = await RetentionService(UserRepository(session)).purge_inactive(now)
            await session.commit()
    finally:
        # Each run gets a new event loop; a pooled asyncpg connection is bound to the old one.
        await engine.dispose()
    # Logged before the marker write, so the deletions are on record even if Redis is down.
    logger.info("purged %d inactive accounts", purged)
    redis = create_redis()
    try:
        await RetentionMarker(redis).record(now)
    finally:
        await redis.aclose()


@celery_app.task(name="accounts.purge_inactive")
def purge_inactive_accounts() -> None:
    asyncio.run(_purge_inactive_accounts())
