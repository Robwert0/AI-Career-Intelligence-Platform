import asyncio
import uuid
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from redis.asyncio import Redis

from app.core.job_store import (
    TERMINAL,
    JobRecord,
    JobStateError,
    JobStatus,
    JobStore,
    effective_state,
)
from app.core.redis import create_redis

NOW = 1_000_000.0
TTL = 600


@pytest_asyncio.fixture
async def redis_client() -> AsyncGenerator[Redis]:
    client = create_redis()
    yield client
    await client.aclose()


@pytest.fixture
def store(redis_client: Redis) -> JobStore:
    return JobStore(redis_client, ttl_seconds=TTL)


@pytest.fixture
def owner() -> str:
    return uuid.uuid4().hex


async def test_create_stores_a_queued_record_with_the_ttl(
    store: JobStore, redis_client: Redis, owner: str
) -> None:
    record = await store.create("ping", owner, now=NOW)

    assert record.status is JobStatus.QUEUED
    assert (record.kind, record.owner_id) == ("ping", owner)
    assert (record.created_at, record.updated_at) == (NOW, NOW)
    assert 0 < await redis_client.ttl(f"job:{record.id}") <= TTL


async def test_ids_are_unguessable_and_unique(store: JobStore, owner: str) -> None:
    ids = {(await store.create("ping", owner, now=NOW)).id for _ in range(50)}

    assert len(ids) == 50
    assert all(len(job_id) == 22 for job_id in ids)


async def test_get_returns_the_record_only_to_its_owner(store: JobStore, owner: str) -> None:
    record = await store.create("ping", owner, now=NOW)

    assert await store.get(record.id, owner) == record
    # None, not an error: a 404 for someone else's job must not reveal that it exists.
    assert await store.get(record.id, "someone-else") is None


async def test_an_unknown_id_is_none(store: JobStore, owner: str) -> None:
    assert await store.get("A" * 22, owner) is None
    assert await store.load("A" * 22) is None


@pytest.mark.parametrize("job_id", ["*", "job:x", "../../etc", "", "A" * 21, "A" * 5000, "a b"])
async def test_malformed_ids_are_rejected_before_redis(
    store: JobStore, redis_client: Redis, owner: str, job_id: str
) -> None:
    await redis_client.set(f"job:{job_id}", b"{}")
    try:
        assert await store.load(job_id) is None
        assert await store.get(job_id, owner) is None
        assert await store.take_blob(job_id, "cv") is None
    finally:
        await redis_client.delete(f"job:{job_id}")


async def test_transitions_update_status_stage_and_time(store: JobStore, owner: str) -> None:
    record = await store.create("ping", owner, now=NOW)

    running = await store.mark_running(record.id, stage="reading", now=NOW + 1)
    assert running is not None
    assert (running.status, running.stage, running.updated_at) == (
        JobStatus.RUNNING,
        "reading",
        NOW + 1,
    )

    done = await store.mark_done(record.id, result={"pong": True}, now=NOW + 2)
    assert done is not None
    assert (done.status, done.result) == (JobStatus.DONE, {"pong": True})
    assert await store.load(record.id) == done


async def test_mark_failed_records_the_error_code(store: JobStore, owner: str) -> None:
    record = await store.create("ping", owner, now=NOW)

    failed = await store.mark_failed(record.id, error_code="fetch_timeout", now=NOW + 1)

    assert failed is not None
    assert (failed.status, failed.error_code) == (JobStatus.FAILED, "fetch_timeout")


async def test_a_transition_keeps_the_original_ttl(
    store: JobStore, redis_client: Redis, owner: str
) -> None:
    record = await store.create("ping", owner, now=NOW)
    await redis_client.expire(f"job:{record.id}", 30)

    await store.mark_running(record.id, stage="reading", now=NOW + 1)

    assert 0 < await redis_client.ttl(f"job:{record.id}") <= 30


async def test_a_transition_never_resurrects_an_expired_record(
    store: JobStore, redis_client: Redis, owner: str
) -> None:
    record = await store.create("ping", owner, now=NOW)
    await redis_client.delete(f"job:{record.id}")

    assert await store.mark_done(record.id, result={}, now=NOW + 1) is None
    assert await redis_client.exists(f"job:{record.id}") == 0


@pytest.mark.parametrize("final", ["done", "failed"])
async def test_a_terminal_record_refuses_further_transitions(
    store: JobStore, owner: str, final: str
) -> None:
    record = await store.create("ping", owner, now=NOW)
    if final == "done":
        await store.mark_done(record.id, result={}, now=NOW + 1)
    else:
        await store.mark_failed(record.id, error_code="x", now=NOW + 1)

    with pytest.raises(JobStateError):
        await store.mark_running(record.id, stage="again", now=NOW + 2)


async def test_a_blob_round_trips_binary_and_is_gone_after_take(
    store: JobStore, redis_client: Redis, owner: str
) -> None:
    record = await store.create("ping", owner, now=NOW)
    payload = b"%PDF-1.7\x00\xff\xfe binary"

    await store.put_blob(record.id, "cv", payload, ttl_seconds=60)

    assert 0 < await redis_client.ttl(f"job:{record.id}:blob:cv") <= 60
    assert await store.take_blob(record.id, "cv") == payload
    assert await store.take_blob(record.id, "cv") is None


async def test_a_blob_never_appears_in_the_record(store: JobStore, owner: str) -> None:
    record = await store.create("ping", owner, now=NOW)
    await store.put_blob(record.id, "cv", b"secret cv bytes", ttl_seconds=60)

    loaded = await store.load(record.id)

    assert loaded is not None
    assert "secret cv bytes" not in loaded.model_dump_json()
    await store.take_blob(record.id, "cv")


@pytest.mark.parametrize("name", ["", "CV", "a:b", "x" * 33])
async def test_an_invalid_blob_name_is_a_programming_error(
    store: JobStore, owner: str, name: str
) -> None:
    record = await store.create("ping", owner, now=NOW)

    with pytest.raises(ValueError):
        await store.put_blob(record.id, name, b"x", ttl_seconds=60)


async def test_a_running_job_past_the_hard_limit_is_shown_as_timed_out(
    store: JobStore, owner: str
) -> None:
    record = await store.create("job_intake", owner, now=NOW)
    running = await store.mark_running(record.id, stage="extracting", now=NOW)
    assert running is not None

    fresh = effective_state(
        running, now=NOW + 100, running_limit_seconds=330, queued_limit_seconds=900
    )
    stale = effective_state(
        running, now=NOW + 331, running_limit_seconds=330, queued_limit_seconds=900
    )

    assert fresh.status is JobStatus.RUNNING
    assert (stale.status, stale.error_code) == (JobStatus.FAILED, "timeout")
    # View-only: effective_state never writes the stale verdict back.
    stored = await store.load(record.id)
    assert stored is not None and stored.status is JobStatus.RUNNING


async def test_a_job_queued_too_long_is_shown_as_queue_unavailable(
    store: JobStore, owner: str
) -> None:
    record = await store.create("job_intake", owner, now=NOW)

    stale = effective_state(
        record, now=NOW + 901, running_limit_seconds=330, queued_limit_seconds=900
    )

    assert (stale.status, stale.error_code) == (JobStatus.FAILED, "queue_unavailable")


async def test_the_queue_cut_off_is_measured_from_the_last_update(
    store: JobStore, owner: str
) -> None:
    record = await store.create("job_intake", owner, now=NOW)
    requeued = record.model_copy(update={"updated_at": NOW + 800})

    view = effective_state(
        requeued, now=NOW + 901, running_limit_seconds=330, queued_limit_seconds=900
    )

    assert view.status is JobStatus.QUEUED


async def test_finished_jobs_are_never_rewritten_by_the_view(store: JobStore, owner: str) -> None:
    record = await store.create("job_intake", owner, now=NOW)
    done = await store.mark_done(record.id, result={"x": 1}, now=NOW)
    assert done is not None

    assert (
        effective_state(done, now=NOW + 99_999, running_limit_seconds=330, queued_limit_seconds=900)
        == done
    )


async def test_an_exclusive_create_claims_a_free_slot_with_the_record(
    store: JobStore, redis_client: Redis, owner: str
) -> None:
    record, holder = await store.create_exclusive(
        "ping", owner, now=NOW, replacing=None, lock_ttl_seconds=30
    )

    assert holder is None
    assert record is not None
    assert await store.get(record.id, owner) == record
    assert await redis_client.get(f"job:active:ping:{owner}") == record.id.encode()
    assert 0 < await redis_client.ttl(f"job:active:ping:{owner}") <= 30


async def test_an_exclusive_create_reports_the_holder_and_writes_nothing(
    store: JobStore, redis_client: Redis, owner: str
) -> None:
    first, _ = await store.create_exclusive(
        "ping", owner, now=NOW, replacing=None, lock_ttl_seconds=30
    )
    assert first is not None
    before = set(await redis_client.keys("job:*"))

    record, holder = await store.create_exclusive(
        "ping", owner, now=NOW, replacing=None, lock_ttl_seconds=30
    )

    assert (record, holder) == (None, first.id)
    assert set(await redis_client.keys("job:*")) == before


async def test_replacing_succeeds_only_while_the_named_holder_still_holds(
    store: JobStore, owner: str
) -> None:
    first, _ = await store.create_exclusive(
        "ping", owner, now=NOW, replacing=None, lock_ttl_seconds=30
    )
    assert first is not None
    second, _ = await store.create_exclusive(
        "ping", owner, now=NOW, replacing=first.id, lock_ttl_seconds=30
    )
    assert second is not None

    late, holder = await store.create_exclusive(
        "ping", owner, now=NOW, replacing=first.id, lock_ttl_seconds=30
    )

    assert (late, holder) == (None, second.id)


async def _paused(store: JobStore, owner: str) -> str:
    record = await store.create("match_analysis", owner, now=NOW)
    await store.mark_running(record.id, stage="reading_cv", now=NOW + 1)
    await store.mark_needs_decision(
        record.id,
        failed_source="cv",
        error_code="scanned_pdf_suspected",
        reset_at=None,
        now=NOW + 2,
    )
    return record.id


async def test_a_paused_job_records_the_failed_source_and_is_not_terminal(
    store: JobStore, owner: str
) -> None:
    job_id = await _paused(store, owner)

    record = await store.load(job_id)

    assert record is not None
    assert record.status is JobStatus.NEEDS_DECISION
    assert (record.failed_source, record.error_code, record.stage) == (
        "cv",
        "scanned_pdf_suspected",
        "reading_cv",
    )
    assert JobStatus.NEEDS_DECISION not in TERMINAL


async def test_resume_requeues_a_paused_job_with_the_directive(store: JobStore, owner: str) -> None:
    job_id = await _paused(store, owner)

    resumed = await store.resume(job_id, owner, resume="continue", now=NOW + 3)

    assert resumed is not None
    stored = await store.load(job_id)
    assert stored == resumed
    assert (stored.status, stored.resume, stored.error_code, stored.failed_source) == (
        JobStatus.QUEUED,
        "continue",
        None,
        "cv",
    )
    assert stored.updated_at == NOW + 3


async def test_resume_is_owner_scoped(store: JobStore, owner: str) -> None:
    job_id = await _paused(store, owner)

    assert await store.resume(job_id, "someone-else", resume="continue", now=NOW + 3) is None
    record = await store.load(job_id)
    assert record is not None
    assert record.status is JobStatus.NEEDS_DECISION


async def test_resume_refuses_a_job_that_is_not_paused(store: JobStore, owner: str) -> None:
    record = await store.create("match_analysis", owner, now=NOW)

    with pytest.raises(JobStateError):
        await store.resume(record.id, owner, resume="retry", now=NOW + 1)


async def test_two_concurrent_resumes_let_exactly_one_through(store: JobStore, owner: str) -> None:
    job_id = await _paused(store, owner)

    outcomes = await asyncio.gather(
        *(store.resume(job_id, owner, resume="retry", now=NOW + 3) for _ in range(5)),
        return_exceptions=True,
    )

    assert sum(isinstance(outcome, JobRecord) for outcome in outcomes) == 1
    assert all(isinstance(outcome, JobRecord | JobStateError) for outcome in outcomes), outcomes


async def test_a_blob_attached_to_a_record_expires_with_it(
    store: JobStore, redis_client: Redis, owner: str
) -> None:
    record = await store.create("match_analysis", owner, now=NOW)

    assert await store.attach_blob(record.id, "sources", b"{}") is True

    record_ttl = await redis_client.pttl(f"job:{record.id}")
    blob_ttl = await redis_client.pttl(f"job:{record.id}:blob:sources")
    assert 0 < blob_ttl <= record_ttl


async def test_an_attached_blob_never_outlives_its_record(
    store: JobStore, redis_client: Redis, owner: str
) -> None:
    for _ in range(20):
        record = await store.create("match_analysis", owner, now=NOW)
        await asyncio.sleep(0.002)

        await store.attach_blob(record.id, "sources", b"{}")

        record_expiry = await redis_client.pexpiretime(f"job:{record.id}")
        blob_expiry = await redis_client.pexpiretime(f"job:{record.id}:blob:sources")
        assert 0 < blob_expiry <= record_expiry


async def test_no_blob_is_attached_to_an_expired_record(
    store: JobStore, redis_client: Redis
) -> None:
    job_id = "B" * 22

    assert await store.attach_blob(job_id, "sources", b"{}") is False
    assert await redis_client.exists(f"job:{job_id}:blob:sources") == 0


async def test_read_blob_leaves_the_blob_in_place(store: JobStore, owner: str) -> None:
    record = await store.create("match_analysis", owner, now=NOW)
    await store.attach_blob(record.id, "analysis_input", b"payload")

    assert await store.read_blob(record.id, "analysis_input") == b"payload"
    assert await store.read_blob(record.id, "analysis_input") == b"payload"


async def test_delete_blobs_removes_every_named_blob(store: JobStore, owner: str) -> None:
    record = await store.create("match_analysis", owner, now=NOW)
    await store.attach_blob(record.id, "sources", b"a")
    await store.put_blob(record.id, "cv_text", b"b", ttl_seconds=60)

    await store.delete_blobs(record.id, "sources", "cv_text", "cv_file")

    assert await store.read_blob(record.id, "sources") is None
    assert await store.read_blob(record.id, "cv_text") is None


async def test_load_many_keeps_order_and_marks_missing_ids(store: JobStore, owner: str) -> None:
    first = await store.create("match_analysis", owner, now=NOW)
    second = await store.create("match_analysis", owner, now=NOW)

    loaded = await store.load_many([second.id, "C" * 22, first.id, "bad id"])

    assert [record.id if record else None for record in loaded] == [second.id, None, first.id, None]


async def test_a_resumed_job_is_not_stale_because_it_was_created_long_ago(
    store: JobStore, owner: str
) -> None:
    job_id = await _paused(store, owner)
    resumed = await store.resume(job_id, owner, resume="continue", now=NOW + 5000)
    assert resumed is not None

    view = effective_state(
        resumed, now=NOW + 5010, running_limit_seconds=100, queued_limit_seconds=900
    )

    assert view.status is JobStatus.QUEUED


async def test_the_first_stage_can_be_left_unset(store: JobStore, owner: str) -> None:
    record = await store.create("match_analysis", owner, now=NOW)

    running = await store.mark_running(record.id, stage=None, now=NOW + 1)

    assert running is not None
    assert running.stage is None


async def test_remaining_seconds_reads_the_records_ttl_without_changing_it(
    store: JobStore, owner: str, redis_client: Redis
) -> None:
    record = await store.create("match_analysis", owner, now=NOW)
    await redis_client.expire(f"job:{record.id}", 90)

    assert 85 <= (await store.remaining_seconds(record.id) or 0) <= 90
    assert await redis_client.ttl(f"job:{record.id}") <= 90


async def test_remaining_seconds_is_none_for_a_missing_or_malformed_record(
    store: JobStore,
) -> None:
    assert await store.remaining_seconds("A" * 22) is None
    assert await store.remaining_seconds("../job:x") is None
