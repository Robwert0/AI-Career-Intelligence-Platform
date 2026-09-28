import time

from app.core.config import settings
from app.core.job_store import JobRecord, JobStore, effective_state
from app.integrations.safe_fetch import parse_public_url
from app.schemas.match import JobIntakeRequest
from app.workers.queue import QueueUnavailableError, TaskQueue

JOB_INTAKE = "job_intake"


class MatchService:
    def __init__(self, store: JobStore, queue: TaskQueue) -> None:
        self._store = store
        self._queue = queue

    async def submit_job(self, owner_id: str, intake: JobIntakeRequest, *, now: float) -> str:
        if intake.url is not None:
            parse_public_url(intake.url)
        record = await self._store.create(JOB_INTAKE, owner_id, now=now)
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

    async def get_job(self, owner_id: str, job_id: str, *, now: float) -> JobRecord | None:
        record = await self._store.get(job_id, owner_id)
        if record is None or record.kind != JOB_INTAKE:
            return None
        return effective_state(
            record,
            now=now,
            running_limit_seconds=settings.job_hard_time_limit_seconds,
            queued_limit_seconds=settings.job_queue_stale_seconds,
        )
