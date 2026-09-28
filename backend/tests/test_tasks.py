import asyncio
from collections.abc import AsyncGenerator
from typing import Any

import pytest
import pytest_asyncio
from celery.exceptions import SoftTimeLimitExceeded
from redis.asyncio import Redis

from app.core.config import settings
from app.core.job_store import JobRecord, JobStatus, JobStore
from app.core.redis import create_redis
from app.workers import tasks
from app.workers.celery_app import celery_app
from app.workers.tasks import JobError, execute_job, ping, run_job

NOW = 1_000_000.0


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
