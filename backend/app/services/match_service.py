import time
from dataclasses import dataclass
from typing import Literal

from app.core.analysis_registry import AnalysisRegistry
from app.core.config import settings
from app.core.job_store import (
    TERMINAL,
    JobRecord,
    JobStateError,
    JobStatus,
    JobStore,
    effective_state,
)
from app.integrations.safe_fetch import parse_public_url
from app.schemas.match import AnalysisInput, JobIntakeRequest
from app.workers.queue import QueueUnavailableError, TaskQueue

JOB_INTAKE = "job_intake"
_CLAIM_ATTEMPTS = 3
ANALYSIS = "match_analysis"
RUN_ANALYSIS = "jobs.run_analysis"
CV_BLOB = {"file": "cv_file", "text": "cv_text"}
RESUMED_BLOBS = ("analysis_input", "sources")
GITHUB_URL_BLOB = "github_url"
DISCARDED_BLOBS = (*RESUMED_BLOBS, *CV_BLOB.values(), GITHUB_URL_BLOB)


@dataclass(frozen=True, slots=True)
class CvUpload:
    kind: Literal["file", "text"]
    data: bytes


@dataclass(frozen=True, slots=True)
class AnalysisView:
    record: JobRecord
    queue_position: int | None


class AnalysisInProgressError(Exception):
    def __init__(self, analysis_id: str) -> None:
        super().__init__(analysis_id)
        self.analysis_id = analysis_id


class NotAwaitingDecisionError(Exception):
    """continue/retry on an analysis that is not paused."""


class RetryUrlNotAllowedError(Exception):
    """A corrected GitHub URL was sent for a source that is not GitHub."""


class QueueFullError(Exception):
    """Too many analyses are already waiting for the worker."""


class AnalysisRunningError(Exception):
    """A running analysis cannot be discarded: the worker is already spending on it."""


class CvRequiredError(Exception):
    """A retry of the CV source needs the CV again: its bytes were deleted after the first read."""


class JobInProgressError(Exception):
    def __init__(self, job_id: str) -> None:
        super().__init__(job_id)
        self.job_id = job_id


def _view(record: JobRecord, now: float) -> JobRecord:
    return effective_state(
        record,
        now=now,
        running_limit_seconds=settings.job_hard_time_limit_seconds,
        queued_limit_seconds=settings.job_queue_stale_seconds,
    )


class MatchService:
    def __init__(self, store: JobStore, queue: TaskQueue, registry: AnalysisRegistry) -> None:
        self._store = store
        self._queue = queue
        self._registry = registry

    async def submit_job(self, owner_id: str, intake: JobIntakeRequest, *, now: float) -> str:
        if intake.url is not None:
            parse_public_url(intake.url)
        record = await self._claim(owner_id, now)
        await self._store.put_blob(
            record.id,
            "input",
            intake.model_dump_json().encode(),
            ttl_seconds=settings.job_ttl_seconds,
        )
        try:
            await self._queue.enqueue("jobs.extract_job", record.id)
        except QueueUnavailableError:
            failed = True
        else:
            failed = False
        if failed:
            await self._store.mark_failed(
                record.id, error_code="queue_unavailable", now=time.time()
            )
            raise QueueUnavailableError("jobs.extract_job")
        return record.id

    async def _claim(self, owner_id: str, now: float) -> JobRecord:
        replacing: str | None = None
        for _ in range(_CLAIM_ATTEMPTS):
            record, holder = await self._store.create_exclusive(
                JOB_INTAKE,
                owner_id,
                now=now,
                replacing=replacing,
                # Past this no holder can still be active: effective_state reports it stale.
                lock_ttl_seconds=settings.job_queue_stale_seconds
                + settings.job_hard_time_limit_seconds,
            )
            if record is not None:
                return record
            assert holder is not None
            current = await self._store.get(holder, owner_id)
            if current is not None and _view(current, now).status not in TERMINAL:
                raise JobInProgressError(holder)
            replacing = holder
        # Every attempt lost to a fresher claim, so another request is submitting right now.
        assert replacing is not None
        raise JobInProgressError(replacing)

    async def get_job(self, owner_id: str, job_id: str, *, now: float) -> JobRecord | None:
        record = await self._store.get(job_id, owner_id)
        if record is None or record.kind != JOB_INTAKE:
            return None
        return _view(record, now)

    def _analysis_view(self, record: JobRecord, now: float) -> JobRecord:
        return effective_state(
            record,
            now=now,
            running_limit_seconds=settings.match_analysis_hard_time_limit_seconds,
            queued_limit_seconds=settings.job_queue_stale_seconds,
        )

    async def _is_active(self, owner_id: str, analysis_id: str, now: float) -> bool:
        record = await self._store.get(analysis_id, owner_id)
        return record is not None and self._analysis_view(record, now).status not in TERMINAL

    async def _claim_analysis(self, owner_id: str, analysis_id: str, now: float) -> None:
        holder = await self._registry.try_lock(owner_id, analysis_id)
        if holder is None:
            return
        # A finished, failed or expired holder no longer blocks: nothing ever has to release it.
        if not await self._is_active(owner_id, holder, now) and await self._registry.replace_lock(
            owner_id, expected=holder, analysis_id=analysis_id
        ):
            return
        await self._store.delete(analysis_id)
        raise AnalysisInProgressError(await self._registry.holder(owner_id) or holder)

    async def _enqueue(self, owner_id: str, analysis_id: str, now: float) -> None:
        await self._registry.mark_queued(analysis_id, now=now)
        try:
            await self._queue.enqueue(RUN_ANALYSIS, analysis_id)
        except QueueUnavailableError:
            failed = True
        else:
            failed = False
        if failed:
            await self._store.mark_failed(
                analysis_id, error_code="queue_unavailable", now=time.time()
            )
            await self._registry.forget(analysis_id)
            await self._registry.release_lock(owner_id, analysis_id)
            raise QueueUnavailableError(RUN_ANALYSIS)

    async def submit_analysis(
        self, owner_id: str, request: AnalysisInput, cv: CvUpload | None, *, now: float
    ) -> str:
        if request.cv_provided != (cv is not None):
            raise ValueError("cv_provided must match the CV that was sent")
        await self._ensure_queue_has_room(now)
        record = await self._store.create(ANALYSIS, owner_id, now=now)
        # The lock comes first, so a refused request never writes CV bytes to Redis.
        await self._claim_analysis(owner_id, record.id, now)
        await self._store.attach_blob(
            record.id, "analysis_input", request.model_dump_json().encode()
        )
        if cv is not None:
            await self._store.put_blob(
                record.id, CV_BLOB[cv.kind], cv.data, ttl_seconds=settings.match_cv_ttl_seconds
            )
        await self._enqueue(owner_id, record.id, now)
        return record.id

    async def _ensure_queue_has_room(self, now: float) -> None:
        # The zset also holds analyses that started or finished since anyone polled them.
        members = await self._registry.queued()
        records = await self._store.load_many(members)
        waiting = [
            analysis_id
            for analysis_id, record in zip(members, records, strict=True)
            if record is not None and self._analysis_view(record, now).status is JobStatus.QUEUED
        ]
        gone = sorted(set(members) - set(waiting))
        if gone:
            await self._registry.forget(*gone)
        if len(waiting) >= settings.match_max_queued_analyses:
            raise QueueFullError

    async def discard_analysis(self, owner_id: str, analysis_id: str, *, now: float) -> str | None:
        """Start over: a queued or paused analysis is failed, its inputs and its lock released."""
        record = await self._store.get(analysis_id, owner_id)
        if record is None or record.kind != ANALYSIS:
            return None
        try:
            discarded = await self._store.discard(analysis_id, owner_id, now=now)
        except JobStateError:
            discarded = None
        if discarded is None:
            raise AnalysisRunningError(analysis_id)
        await self._store.delete_blobs(analysis_id, *DISCARDED_BLOBS)
        await self._registry.forget(analysis_id)
        await self._registry.release_lock(owner_id, analysis_id)
        return analysis_id

    async def _queue_position(self, record: JobRecord, now: float) -> int | None:
        if record.status is not JobStatus.QUEUED:
            await self._registry.forget(record.id)
            return None
        ahead = await self._registry.queued_before(record.id)
        if ahead is None:
            return None
        records = await self._store.load_many(ahead)
        gone = [
            analysis_id
            for analysis_id, other in zip(ahead, records, strict=True)
            if other is None or self._analysis_view(other, now).status is not JobStatus.QUEUED
        ]
        if gone:
            await self._registry.forget(*gone)
        return len(ahead) - len(gone)

    async def get_analysis(
        self, owner_id: str, analysis_id: str, *, now: float
    ) -> AnalysisView | None:
        record = await self._store.get(analysis_id, owner_id)
        if record is None or record.kind != ANALYSIS:
            return None
        view = self._analysis_view(record, now)
        return AnalysisView(record=view, queue_position=await self._queue_position(view, now))

    async def _resume(
        self,
        owner_id: str,
        analysis_id: str,
        resume: str,
        cv: CvUpload | None,
        *,
        now: float,
        github_url: str | None = None,
    ) -> str | None:
        record = await self._store.get(analysis_id, owner_id)
        if record is None or record.kind != ANALYSIS:
            return None
        if record.status is not JobStatus.NEEDS_DECISION:
            raise NotAwaitingDecisionError(analysis_id)
        needs_cv = resume == "retry" and record.failed_source == "cv"
        if needs_cv and cv is None:
            raise CvRequiredError(analysis_id)
        if github_url is not None and not (resume == "retry" and record.failed_source == "github"):
            raise RetryUrlNotAllowedError(analysis_id)
        blob: tuple[str, bytes, int] | None = None
        if needs_cv and cv is not None:
            blob = (CV_BLOB[cv.kind], cv.data, settings.match_cv_ttl_seconds)
        elif github_url is not None:
            blob = (GITHUB_URL_BLOB, github_url.encode(), settings.job_ttl_seconds)
        try:
            resumed = await self._store.resume(
                analysis_id,
                owner_id,
                resume=resume,
                now=now,
                blob=blob,
                # Queued, then run: the worst case the record must outlive once resumed.
                min_ttl_seconds=settings.job_queue_stale_seconds
                + settings.match_analysis_hard_time_limit_seconds,
                keep_blobs=RESUMED_BLOBS,
            )
        except JobStateError:
            resumed = None
        if resumed is None:
            raise NotAwaitingDecisionError(analysis_id)
        await self._enqueue(owner_id, analysis_id, now)
        return analysis_id

    async def continue_analysis(self, owner_id: str, analysis_id: str, *, now: float) -> str | None:
        return await self._resume(owner_id, analysis_id, "continue", None, now=now)

    async def retry_analysis(
        self,
        owner_id: str,
        analysis_id: str,
        cv: CvUpload | None,
        *,
        now: float,
        github_url: str | None = None,
    ) -> str | None:
        return await self._resume(
            owner_id, analysis_id, "retry", cv, now=now, github_url=github_url
        )
