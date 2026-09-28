import re
import secrets
from collections.abc import Callable, Sequence
from enum import StrEnum
from typing import Any, cast

from pydantic import BaseModel, ConfigDict
from redis.asyncio import Redis
from redis.exceptions import WatchError

JobStatus = StrEnum("JobStatus", ("QUEUED", "RUNNING", "NEEDS_DECISION", "DONE", "FAILED"))
TERMINAL = frozenset({JobStatus.DONE, JobStatus.FAILED})

# token_urlsafe(16) is always 22 characters; anything else never reaches Redis.
_ID = re.compile(r"[A-Za-z0-9_-]{22}")
_BLOB_NAME = re.compile(r"[a-z_]{1,32}")
_WRITE_ATTEMPTS = 3
# One script, so the blob gets the record's exact expiry: time is frozen while it runs.
_ATTACH_LUA = """
local remaining = redis.call('PTTL', KEYS[1])
if remaining <= 0 then
  return 0
end
redis.call('SET', KEYS[2], ARGV[1], 'PX', remaining)
return 1
"""

# The record and the slot are written together, so a slot never names a record that was
# never created. ARGV[1] is the holder the caller saw finished ("" for none).
_CREATE_EXCLUSIVE_LUA = """
local holder = redis.call('GET', KEYS[1])
if holder and holder ~= ARGV[1] then
  return holder
end
redis.call('SET', KEYS[1], ARGV[2], 'EX', ARGV[3])
redis.call('SET', KEYS[2], ARGV[4], 'EX', ARGV[5])
return false
"""


class JobRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    kind: str
    owner_id: str
    status: JobStatus
    stage: str | None = None
    error_code: str | None = None
    result: dict[str, Any] | None = None
    failed_source: str | None = None
    reset_at: int | None = None
    resume: str | None = None
    created_at: float
    updated_at: float


class JobStateError(Exception):
    """A finished job cannot change; a redelivered task must treat it as already handled."""


class JobStore:
    def __init__(self, redis: Redis, *, ttl_seconds: int) -> None:
        self._redis = redis
        self._ttl = ttl_seconds
        self._create_exclusive = redis.register_script(_CREATE_EXCLUSIVE_LUA)
        self._attach = redis.register_script(_ATTACH_LUA)

    @staticmethod
    def _key(job_id: str) -> str:
        return f"job:{job_id}"

    @staticmethod
    def _blob_key(job_id: str, name: str) -> str:
        return f"job:{job_id}:blob:{name}"

    @staticmethod
    def _slot_key(kind: str, owner_id: str) -> str:
        return f"job:active:{kind}:{owner_id}"

    @staticmethod
    def _valid_blob(job_id: str, name: str) -> bool:
        return bool(_ID.fullmatch(job_id) and _BLOB_NAME.fullmatch(name))

    @staticmethod
    def _new(kind: str, owner_id: str, now: float) -> JobRecord:
        return JobRecord(
            id=secrets.token_urlsafe(16),
            kind=kind,
            owner_id=owner_id,
            status=JobStatus.QUEUED,
            created_at=now,
            updated_at=now,
        )

    async def create(self, kind: str, owner_id: str, *, now: float) -> JobRecord:
        record = self._new(kind, owner_id, now)
        await self._redis.set(self._key(record.id), record.model_dump_json(), ex=self._ttl)
        return record

    async def create_exclusive(
        self,
        kind: str,
        owner_id: str,
        *,
        now: float,
        replacing: str | None,
        lock_ttl_seconds: int,
    ) -> tuple[JobRecord | None, str | None]:
        """Create the owner's one active job of this kind, or return the id holding the slot."""
        record = self._new(kind, owner_id, now)
        holder = await self._create_exclusive(
            keys=[self._slot_key(kind, owner_id), self._key(record.id)],
            args=[
                replacing or "",
                record.id,
                min(lock_ttl_seconds, self._ttl),
                record.model_dump_json(),
                self._ttl,
            ],
        )
        if holder is None:
            return record, None
        return None, holder.decode()

    async def load(self, job_id: str) -> JobRecord | None:
        if not _ID.fullmatch(job_id):
            return None
        raw = await self._redis.get(self._key(job_id))
        return None if raw is None else JobRecord.model_validate_json(raw)

    async def load_many(self, job_ids: Sequence[str]) -> list[JobRecord | None]:
        valid = [job_id for job_id in job_ids if _ID.fullmatch(job_id)]
        raws = await self._redis.mget([self._key(job_id) for job_id in valid]) if valid else []
        by_id = {
            job_id: JobRecord.model_validate_json(raw)
            for job_id, raw in zip(valid, raws, strict=True)
            if raw is not None
        }
        return [by_id.get(job_id) for job_id in job_ids]

    async def get(self, job_id: str, owner_id: str) -> JobRecord | None:
        record = await self.load(job_id)
        if record is None or record.owner_id != owner_id:
            return None
        return record

    async def delete(self, job_id: str) -> None:
        if _ID.fullmatch(job_id):
            await self._redis.delete(self._key(job_id))

    async def mark_running(self, job_id: str, *, stage: str | None, now: float) -> JobRecord | None:
        return await self._transition(job_id, now, status=JobStatus.RUNNING, stage=stage)

    async def mark_done(
        self, job_id: str, *, result: dict[str, Any], now: float
    ) -> JobRecord | None:
        return await self._transition(job_id, now, status=JobStatus.DONE, result=result)

    async def mark_failed(self, job_id: str, *, error_code: str, now: float) -> JobRecord | None:
        return await self._transition(job_id, now, status=JobStatus.FAILED, error_code=error_code)

    async def mark_needs_decision(
        self,
        job_id: str,
        *,
        failed_source: str,
        error_code: str,
        reset_at: int | None,
        now: float,
    ) -> JobRecord | None:
        return await self._transition(
            job_id,
            now,
            status=JobStatus.NEEDS_DECISION,
            failed_source=failed_source,
            error_code=error_code,
            reset_at=reset_at,
            resume=None,
        )

    async def resume(
        self,
        job_id: str,
        owner_id: str,
        *,
        resume: str,
        now: float,
        blob: tuple[str, bytes, int] | None = None,
        min_ttl_seconds: int = 0,
        keep_blobs: tuple[str, ...] = (),
    ) -> JobRecord | None:
        """needs_decision -> queued, atomically. `blob` (name, data, ttl) is written in the same
        transaction, so a request that loses the race writes nothing at all. The record and
        `keep_blobs` are extended to at least `min_ttl_seconds`, so a job resumed near the end of
        its life can still queue and run."""
        if blob is not None and not self._valid_blob(job_id, blob[0]):
            raise ValueError("invalid job id or blob name")

        def change(record: JobRecord) -> JobRecord | None:
            if record.owner_id != owner_id:
                return None
            if record.status is not JobStatus.NEEDS_DECISION:
                raise JobStateError(f"job {job_id} is {record.status}, not awaiting a decision")
            return record.model_copy(
                update={
                    "status": JobStatus.QUEUED,
                    "resume": resume,
                    "error_code": None,
                    "reset_at": None,
                    "updated_at": now,
                }
            )

        extra = None
        if blob is not None:
            name, data, ttl = blob
            extra = (self._blob_key(job_id, name), data, ttl)
        extend = [
            self._key(job_id),
            *(
                self._blob_key(job_id, name)
                for name in keep_blobs
                if self._valid_blob(job_id, name)
            ),
        ]
        return await self._compare_and_set(
            job_id,
            change,
            extra=extra,
            extend=(extend, min_ttl_seconds) if min_ttl_seconds else None,
        )

    async def _transition(self, job_id: str, now: float, **changes: Any) -> JobRecord | None:
        def change(record: JobRecord) -> JobRecord:
            if record.status in TERMINAL:
                raise JobStateError(f"job {job_id} is already {record.status}")
            return record.model_copy(update={**changes, "updated_at": now})

        return await self._compare_and_set(job_id, change)

    async def _compare_and_set(
        self,
        job_id: str,
        change: Callable[[JobRecord], JobRecord | None],
        *,
        extra: tuple[str, bytes, int] | None = None,
        extend: tuple[list[str], int] | None = None,
    ) -> JobRecord | None:
        # WATCH makes the read-modify-write atomic now that the API writes too (resume).
        if not _ID.fullmatch(job_id):
            return None
        key = self._key(job_id)
        for _ in range(_WRITE_ATTEMPTS):
            async with self._redis.pipeline(transaction=True) as pipe:
                await pipe.watch(key)
                raw = await pipe.get(key)
                if raw is None:
                    return None
                updated = change(JobRecord.model_validate_json(raw))
                if updated is None:
                    return None
                pipe.multi()  # type: ignore[no-untyped-call]
                # xx: never recreate an expired key; keepttl: never extend its lifetime.
                pipe.set(key, updated.model_dump_json(), xx=True, keepttl=True)
                if extra is not None:
                    pipe.set(extra[0], extra[1], ex=extra[2])
                if extend is not None:
                    # gt: only ever lengthens a life, never shortens one.
                    for extended in extend[0]:
                        pipe.expire(extended, extend[1], gt=True)
                try:
                    stored, *_ = await pipe.execute()
                except WatchError:
                    continue
                return updated if stored else None
        raise JobStateError(f"job {job_id} kept changing while being written")

    async def put_blob(self, job_id: str, name: str, data: bytes, *, ttl_seconds: int) -> None:
        if not self._valid_blob(job_id, name):
            raise ValueError("invalid job id or blob name")
        await self._redis.set(self._blob_key(job_id, name), data, ex=ttl_seconds)

    async def attach_blob(self, job_id: str, name: str, data: bytes) -> bool:
        """Stores a blob that expires with its record, never later."""
        if not self._valid_blob(job_id, name):
            raise ValueError("invalid job id or blob name")
        attached = await self._attach(
            keys=[self._key(job_id), self._blob_key(job_id, name)], args=[data]
        )
        return bool(attached)

    async def read_blob(self, job_id: str, name: str) -> bytes | None:
        if not self._valid_blob(job_id, name):
            return None
        return cast(bytes | None, await self._redis.get(self._blob_key(job_id, name)))

    async def take_blob(self, job_id: str, name: str) -> bytes | None:
        if not self._valid_blob(job_id, name):
            return None
        # create_redis() never sets decode_responses, so values come back as bytes.
        return cast(bytes | None, await self._redis.getdel(self._blob_key(job_id, name)))

    async def delete_blobs(self, job_id: str, *names: str) -> None:
        keys = [self._blob_key(job_id, name) for name in names if self._valid_blob(job_id, name)]
        if keys:
            await self._redis.delete(*keys)


def queue_is_stale(record: JobRecord, *, now: float, limit_seconds: int) -> bool:
    # The API and the worker both judge by this, so they can never disagree. updated_at, not
    # created_at: a resumed job is queued again long after it was created.
    return record.status is JobStatus.QUEUED and now - record.updated_at > limit_seconds


def effective_state(
    record: JobRecord, *, now: float, running_limit_seconds: int, queued_limit_seconds: int
) -> JobRecord:
    # A hard time-limit kill runs none of the worker's code, so only the reader can notice.
    if record.status is JobStatus.RUNNING and now - record.updated_at > running_limit_seconds:
        return record.model_copy(update={"status": JobStatus.FAILED, "error_code": "timeout"})
    if queue_is_stale(record, now=now, limit_seconds=queued_limit_seconds):
        return record.model_copy(
            update={"status": JobStatus.FAILED, "error_code": "queue_unavailable"}
        )
    return record
