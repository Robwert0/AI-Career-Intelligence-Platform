import re
import secrets
from enum import StrEnum
from typing import Any, cast

from pydantic import BaseModel, ConfigDict
from redis.asyncio import Redis

JobStatus = StrEnum("JobStatus", ("QUEUED", "RUNNING", "DONE", "FAILED"))
TERMINAL = frozenset({JobStatus.DONE, JobStatus.FAILED})

# token_urlsafe(16) is always 22 characters; anything else never reaches Redis.
_ID = re.compile(r"[A-Za-z0-9_-]{22}")
_BLOB_NAME = re.compile(r"[a-z_]{1,32}")

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
    created_at: float
    updated_at: float


class JobStateError(Exception):
    """A finished job cannot change; a redelivered task must treat it as already handled."""


class JobStore:
    def __init__(self, redis: Redis, *, ttl_seconds: int) -> None:
        self._redis = redis
        self._ttl = ttl_seconds
        self._create_exclusive = redis.register_script(_CREATE_EXCLUSIVE_LUA)

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

    async def get(self, job_id: str, owner_id: str) -> JobRecord | None:
        record = await self.load(job_id)
        if record is None or record.owner_id != owner_id:
            return None
        return record

    async def mark_running(self, job_id: str, *, stage: str, now: float) -> JobRecord | None:
        return await self._transition(job_id, now, status=JobStatus.RUNNING, stage=stage)

    async def mark_done(
        self, job_id: str, *, result: dict[str, Any], now: float
    ) -> JobRecord | None:
        return await self._transition(job_id, now, status=JobStatus.DONE, result=result)

    async def mark_failed(self, job_id: str, *, error_code: str, now: float) -> JobRecord | None:
        return await self._transition(job_id, now, status=JobStatus.FAILED, error_code=error_code)

    async def _transition(self, job_id: str, now: float, **changes: Any) -> JobRecord | None:
        # Read-modify-write is safe only because the worker is the sole writer after create().
        record = await self.load(job_id)
        if record is None:
            return None
        if record.status in TERMINAL:
            raise JobStateError(f"job {job_id} is already {record.status}")
        updated = record.model_copy(update={**changes, "updated_at": now})
        # xx: never recreate an expired key; keepttl: never extend its lifetime.
        stored = await self._redis.set(
            self._key(job_id), updated.model_dump_json(), xx=True, keepttl=True
        )
        return updated if stored else None

    async def put_blob(self, job_id: str, name: str, data: bytes, *, ttl_seconds: int) -> None:
        if not _ID.fullmatch(job_id) or not _BLOB_NAME.fullmatch(name):
            raise ValueError("invalid job id or blob name")
        await self._redis.set(self._blob_key(job_id, name), data, ex=ttl_seconds)

    async def take_blob(self, job_id: str, name: str) -> bytes | None:
        if not _ID.fullmatch(job_id) or not _BLOB_NAME.fullmatch(name):
            return None
        # create_redis() never sets decode_responses, so values come back as bytes.
        return cast(bytes | None, await self._redis.getdel(self._blob_key(job_id, name)))


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
