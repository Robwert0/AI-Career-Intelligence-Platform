import asyncio
import logging
import time
from collections.abc import AsyncGenerator
from typing import Any

import pytest
import pytest_asyncio
import redis.exceptions
from celery.exceptions import SoftTimeLimitExceeded
from fakes import ScriptedGenerator
from redis.asyncio import Redis

from app.core.config import settings
from app.core.job_store import JobRecord, JobStatus, JobStore
from app.core.redis import create_redis
from app.schemas.match import JobIntakeRequest
from app.workers import tasks
from app.workers.celery_app import celery_app
from app.workers.tasks import JobError, execute_job, ping, run_job

NOW = time.time()


@pytest_asyncio.fixture
async def redis_client() -> AsyncGenerator[Redis]:
    client = create_redis()
    yield client
    await client.aclose()


@pytest.fixture
def store(redis_client: Redis) -> JobStore:
    return JobStore(redis_client, ttl_seconds=600)


async def test_a_successful_handler_marks_the_job_done(store: JobStore) -> None:
    record = await store.create("ping", "owner", now=NOW)
    seen: list[JobStatus] = []

    async def handler(store: JobStore, current: JobRecord) -> dict[str, Any]:
        seen.append(current.status)
        return {"answer": 42}

    await execute_job(store, record.id, handler, stage="thinking")

    done = await store.load(record.id)
    assert done is not None
    assert seen == [JobStatus.RUNNING]
    assert (done.status, done.result, done.stage) == (JobStatus.DONE, {"answer": 42}, "thinking")


async def test_a_job_error_becomes_the_failure_code(store: JobStore) -> None:
    record = await store.create("ping", "owner", now=NOW)

    async def handler(store: JobStore, current: JobRecord) -> dict[str, Any]:
        raise JobError("fetch_timeout")

    await execute_job(store, record.id, handler, stage="fetching")

    failed = await store.load(record.id)
    assert failed is not None
    assert (failed.status, failed.error_code) == (JobStatus.FAILED, "fetch_timeout")


async def test_an_unexpected_error_is_recorded_without_its_message(
    store: JobStore, caplog: pytest.LogCaptureFixture
) -> None:
    record = await store.create("ping", "owner", now=NOW)

    async def handler(store: JobStore, current: JobRecord) -> dict[str, Any]:
        raise RuntimeError("Jane Doe, CNP 1960101223344, jane@example.com")

    with caplog.at_level("DEBUG"):
        await execute_job(store, record.id, handler, stage="parsing")

    failed = await store.load(record.id)
    assert failed is not None
    assert (failed.status, failed.error_code) == (JobStatus.FAILED, "internal_error")
    assert "RuntimeError" in caplog.text
    assert "Jane Doe" not in caplog.text
    assert "1960101223344" not in caplog.text


async def test_a_soft_time_limit_inside_the_handler_is_a_timeout(store: JobStore) -> None:
    record = await store.create("ping", "owner", now=NOW)

    async def handler(store: JobStore, current: JobRecord) -> dict[str, Any]:
        raise SoftTimeLimitExceeded()

    await execute_job(store, record.id, handler, stage="assessing")

    failed = await store.load(record.id)
    assert failed is not None
    assert failed.error_code == "timeout"


async def test_an_expired_job_is_skipped_without_running_the_handler(store: JobStore) -> None:
    called = False

    async def handler(store: JobStore, current: JobRecord) -> dict[str, Any]:
        nonlocal called
        called = True
        return {}

    await execute_job(store, "A" * 22, handler, stage="x")

    assert called is False


async def test_a_redelivered_task_for_a_finished_job_is_a_no_op(store: JobStore) -> None:
    record = await store.create("ping", "owner", now=NOW)
    await store.mark_done(record.id, result={"first": True}, now=NOW + 1)

    async def handler(store: JobStore, current: JobRecord) -> dict[str, Any]:
        raise AssertionError("a finished job must not run again")

    await execute_job(store, record.id, handler, stage="x")

    finished = await store.load(record.id)
    assert finished is not None
    assert finished.result == {"first": True}


async def test_a_job_that_expires_mid_run_is_not_recreated(
    store: JobStore, redis_client: Redis
) -> None:
    record = await store.create("ping", "owner", now=NOW)

    async def handler(store: JobStore, current: JobRecord) -> dict[str, Any]:
        await redis_client.delete(f"job:{current.id}")
        return {"late": True}

    await execute_job(store, record.id, handler, stage="x")

    assert await redis_client.exists(f"job:{record.id}") == 0


async def test_a_job_queued_past_the_stale_cut_off_never_runs(
    store: JobStore, caplog: pytest.LogCaptureFixture
) -> None:
    record = await store.create(
        "ping", "owner", now=time.time() - settings.job_queue_stale_seconds - 5
    )

    async def handler(store: JobStore, current: JobRecord) -> dict[str, Any]:
        raise AssertionError("the API already reported this job as unavailable")

    with caplog.at_level(logging.INFO):
        await execute_job(store, record.id, handler, stage="x")

    failed = await store.load(record.id)
    assert failed is not None
    assert (failed.status, failed.error_code, failed.stage) == (
        JobStatus.FAILED,
        "queue_unavailable",
        None,
    )
    assert f"job failed job_id={record.id} error_code=queue_unavailable" in caplog.text


async def test_a_job_queued_just_inside_the_cut_off_still_runs(store: JobStore) -> None:
    record = await store.create(
        "ping", "owner", now=time.time() - settings.job_queue_stale_seconds + 30
    )

    async def handler(store: JobStore, current: JobRecord) -> dict[str, Any]:
        return {"ran": True}

    await execute_job(store, record.id, handler, stage="x")

    done = await store.load(record.id)
    assert done is not None
    assert done.status is JobStatus.DONE


# Sync tests from here on: run_job calls asyncio.run, which refuses to start inside the event loop
# an async test already runs. This is also why the API must never execute tasks eagerly.


def _create_job() -> str:
    async def create() -> str:
        redis = create_redis()
        try:
            store = JobStore(redis, ttl_seconds=600)
            return (await store.create("ping", "owner", now=NOW)).id
        finally:
            await redis.aclose()

    return asyncio.run(create())


def _load(job_id: str) -> JobRecord | None:
    async def load() -> JobRecord | None:
        redis = create_redis()
        try:
            return await JobStore(redis, ttl_seconds=600).load(job_id)
        finally:
            await redis.aclose()

    return asyncio.run(load())


def test_the_ping_task_runs_end_to_end_and_returns_nothing() -> None:
    job_id = _create_job()

    outcome = ping.apply(args=(job_id,))

    # Celery logs a task's return value; tasks return None so a result can never leak into logs.
    assert outcome.result is None
    done = _load(job_id)
    assert done is not None
    assert (done.status, done.result) == (JobStatus.DONE, {"pong": True})


def test_a_soft_time_limit_outside_the_handler_still_marks_the_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_id = _create_job()

    async def interrupted(*args: object, **kwargs: object) -> None:
        raise SoftTimeLimitExceeded()

    monkeypatch.setattr(tasks, "execute_job", interrupted)

    async def unused(store: JobStore, record: JobRecord) -> dict[str, Any]:
        return {}

    run_job(job_id, unused, stage="x")

    failed = _load(job_id)
    assert failed is not None
    assert (failed.status, failed.error_code) == (JobStatus.FAILED, "timeout")


def test_the_celery_app_is_configured_for_id_only_json_tasks() -> None:
    conf = celery_app.conf

    assert conf.broker_url == settings.celery_broker_url
    assert conf.task_serializer == "json"
    assert list(conf.accept_content) == ["json"]
    assert conf.task_ignore_result is True
    assert conf.task_acks_late is True
    assert conf.task_reject_on_worker_lost is True
    assert conf.worker_prefetch_multiplier == 1
    assert conf.worker_concurrency == 1
    assert conf.task_soft_time_limit == settings.job_soft_time_limit_seconds
    assert conf.task_time_limit > conf.task_soft_time_limit
    assert "jobs.ping" in celery_app.tasks


async def test_a_job_found_running_was_orphaned_by_a_crash_and_is_not_rerun(
    store: JobStore,
) -> None:
    record = await store.create("ping", "owner", now=NOW)
    await store.mark_running(record.id, stage="parsing", now=NOW + 1)

    async def handler(store: JobStore, current: JobRecord) -> dict[str, Any]:
        raise AssertionError("an input that crashed the worker must not run again")

    await execute_job(store, record.id, handler, stage="parsing")

    failed = await store.load(record.id)
    assert failed is not None
    assert (failed.status, failed.error_code) == (JobStatus.FAILED, "worker_lost")


async def test_an_unserializable_result_fails_the_job_instead_of_leaving_it_running(
    store: JobStore,
) -> None:
    record = await store.create("ping", "owner", now=NOW)

    async def handler(store: JobStore, current: JobRecord) -> dict[str, Any]:
        return {"score": object()}

    await execute_job(store, record.id, handler, stage="scoring")

    failed = await store.load(record.id)
    assert failed is not None
    assert (failed.status, failed.error_code) == (JobStatus.FAILED, "internal_error")


async def test_a_job_finished_elsewhere_during_the_run_keeps_the_first_outcome(
    store: JobStore,
) -> None:
    record = await store.create("ping", "owner", now=NOW)

    async def handler(store: JobStore, current: JobRecord) -> dict[str, Any]:
        await store.mark_failed(current.id, error_code="worker_lost", now=NOW + 1)
        return {"late": True}

    await execute_job(store, record.id, handler, stage="x")

    finished = await store.load(record.id)
    assert finished is not None
    assert finished.error_code == "worker_lost"


class _StoreThatCannotRecordFailure(JobStore):
    async def mark_failed(self, job_id: str, *, error_code: str, now: float) -> JobRecord | None:
        raise redis.exceptions.TimeoutError("redis blip")


async def _leaks_pii(store: JobStore, record: JobRecord) -> dict[str, Any]:
    raise RuntimeError("Jane Doe, CNP 1960101223344")


@celery_app.task(name="tests.leaks_pii")
def _leaky_task(job_id: str) -> None:
    run_job(job_id, _leaks_pii, stage="parsing")


def test_a_store_failure_after_a_handler_error_never_chains_the_handler_message(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    job_id = _create_job()
    monkeypatch.setattr(tasks, "JobStore", _StoreThatCannotRecordFailure)

    with caplog.at_level("DEBUG"):
        outcome = _leaky_task.apply(args=(job_id,))

    # Celery logs the full chained traceback of whatever escapes the task.
    assert outcome.traceback is not None
    assert "Jane Doe" not in str(outcome.traceback)
    assert "Jane Doe" not in caplog.text


_POSTING_REPLY = (
    '{"is_job_posting": true, "title": "Backend Engineer", "company": null, '
    '"responsibilities": [], "required": [{"text": "Go", "sensitive": false}], "preferred": []}'
)


def _create_intake_job(intake: JobIntakeRequest | None) -> str:
    async def create() -> str:
        redis = create_redis()
        try:
            store = JobStore(redis, ttl_seconds=600)
            record = await store.create("job_intake", "owner", now=NOW)
            if intake is not None:
                await store.put_blob(
                    record.id, "input", intake.model_dump_json().encode(), ttl_seconds=600
                )
            return record.id
        finally:
            await redis.aclose()

    return asyncio.run(create())


def test_the_extract_task_turns_pasted_text_into_a_posting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(tasks, "OllamaGenerator", lambda **_: ScriptedGenerator([_POSTING_REPLY]))
    job_id = _create_intake_job(JobIntakeRequest(text="We build payment systems in Go. " * 5))

    tasks.extract_job_task.apply(args=(job_id,))

    done = _load(job_id)
    assert done is not None
    assert done.status is JobStatus.DONE
    assert done.result is not None
    assert done.result["posting"]["title"] == "Backend Engineer"
    assert done.stage == "extracting"


def test_the_extract_task_consumes_its_input_blob(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tasks, "OllamaGenerator", lambda **_: ScriptedGenerator([_POSTING_REPLY]))
    job_id = _create_intake_job(JobIntakeRequest(text="We build payment systems in Go. " * 5))

    tasks.extract_job_task.apply(args=(job_id,))

    async def blob() -> bytes | None:
        redis = create_redis()
        try:
            return await JobStore(redis, ttl_seconds=600).take_blob(job_id, "input")
        finally:
            await redis.aclose()

    assert asyncio.run(blob()) is None


def test_an_intake_job_without_its_input_fails_as_input_expired() -> None:
    # Distinct from "expired", which means the posting itself was taken down.
    job_id = _create_intake_job(None)

    tasks.extract_job_task.apply(args=(job_id,))

    failed = _load(job_id)
    assert failed is not None
    assert (failed.status, failed.error_code) == (JobStatus.FAILED, "input_expired")


def test_the_extract_task_is_registered() -> None:
    assert "jobs.extract_job" in celery_app.tasks
