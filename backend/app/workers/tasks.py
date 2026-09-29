import asyncio
import contextlib
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any, Literal

from celery.exceptions import SoftTimeLimitExceeded

from app.ai.ollama import OllamaGenerator
from app.core.config import settings
from app.core.job_store import (
    TERMINAL,
    JobRecord,
    JobStateError,
    JobStatus,
    JobStore,
    queue_is_stale,
)
from app.core.redis import create_redis
from app.integrations.safe_fetch import SafeFetcher
from app.schemas.match import JobIntakeRequest
from app.services.job_intake_service import IntakeError, run_job_intake
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

JobHandler = Callable[[JobStore, JobRecord], Awaitable[dict[str, Any]]]
Outcome = Literal["done", "lost", "failed"]


class JobError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


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
    try:
        result = await handler(store, record)
    except JobError as exc:
        return "failed", exc.code, None
    except SoftTimeLimitExceeded:
        return "failed", "timeout", None
    except Exception as exc:
        return "failed", "internal_error", type(exc).__name__

    try:
        with contextlib.suppress(JobStateError):
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
    if record.status in TERMINAL:
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
        "job done job_id=%s kind=%s duration_ms=%d",
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
