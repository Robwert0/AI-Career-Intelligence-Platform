import time

from app.core.config import settings
from app.core.job_store import TERMINAL, JobRecord, JobStore, effective_state
from app.integrations.safe_fetch import parse_public_url
from app.schemas.match import JobIntakeRequest
from app.workers.queue import QueueUnavailableError, TaskQueue

JOB_INTAKE = "job_intake"
_CLAIM_ATTEMPTS = 3


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
    def __init__(self, store: JobStore, queue: TaskQueue) -> None:
        self._store = store
        self._queue = queue

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
