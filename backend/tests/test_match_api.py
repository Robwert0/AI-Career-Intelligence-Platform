import asyncio
import time
import uuid
from collections.abc import AsyncGenerator

import httpx
import pytest
import pytest_asyncio
from fakes import AllowAllLimiter, FakeTaskQueue
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import get_db
from app.core.job_store import JobRecord, JobStatus, JobStore
from app.core.redis import create_redis
from app.deps import get_current_user, get_job_store, get_limiter, get_task_queue
from app.main import app
from app.models import User

PASSWORD = "supersecret1"
TEXT = "Backend Engineer at Acme. We need Go, PostgreSQL and Redis experience. " * 3

MatchFixture = tuple[httpx.AsyncClient, FakeTaskQueue, JobStore, dict[str, str], AllowAllLimiter]


async def _login(client: httpx.AsyncClient, email: str) -> dict[str, str]:
    await client.post("/auth/register", json={"email": email, "password": PASSWORD})
    login = await client.post("/auth/login", json={"email": email, "password": PASSWORD})
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


@pytest_asyncio.fixture
async def redis_client() -> AsyncGenerator[Redis]:
    client = create_redis()
    yield client
    await client.aclose()


@pytest_asyncio.fixture
async def match_client(
    db_session: AsyncSession, allow_all_limiter: AllowAllLimiter, redis_client: Redis
) -> AsyncGenerator[MatchFixture]:
    async def override_get_db() -> AsyncGenerator[AsyncSession]:
        yield db_session
        await db_session.commit()

    queue = FakeTaskQueue()
    store = JobStore(redis_client, ttl_seconds=settings.job_ttl_seconds)
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_limiter] = lambda: allow_all_limiter
    app.dependency_overrides[get_task_queue] = lambda: queue
    app.dependency_overrides[get_job_store] = lambda: store
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://test") as client:
        headers = await _login(client, "match@test.dev")
        allow_all_limiter.calls.clear()
        yield client, queue, store, headers, allow_all_limiter
    app.dependency_overrides.clear()


async def test_submitting_a_url_enqueues_an_intake_job(match_client: MatchFixture) -> None:
    client, queue, store, headers, _ = match_client

    response = await client.post(
        "/match/jobs", json={"url": "https://jobs.example.com/1"}, headers=headers
    )

    assert response.status_code == 202
    job_id = response.json()["job_id"]
    assert queue.enqueued == [("jobs.extract_job", job_id)]
    record = await store.load(job_id)
    assert record is not None
    assert (record.kind, record.status) == ("job_intake", JobStatus.QUEUED)
    assert await store.take_blob(job_id, "input") == (
        b'{"url":"https://jobs.example.com/1","text":null}'
    )


async def test_submitting_pasted_text_enqueues_an_intake_job(match_client: MatchFixture) -> None:
    client, queue, _, headers, _ = match_client

    response = await client.post("/match/jobs", json={"text": TEXT}, headers=headers)

    assert response.status_code == 202
    assert len(queue.enqueued) == 1


async def test_intake_is_rate_limited_per_user(match_client: MatchFixture) -> None:
    client, _, _, headers, limiter = match_client

    await client.post("/match/jobs", json={"text": TEXT}, headers=headers)

    assert [name for name, _ in limiter.calls] == ["match_job_user"]


async def test_polling_fires_both_an_ip_policy_and_a_user_policy(
    match_client: MatchFixture,
) -> None:
    client, _, _, headers, limiter = match_client
    job_id = (await client.post("/match/jobs", json={"text": TEXT}, headers=headers)).json()[
        "job_id"
    ]
    limiter.calls.clear()

    response = await client.get(f"/match/jobs/{job_id}", headers=headers)

    assert response.status_code == 200
    fired = dict(limiter.calls)
    assert set(fired) == {"match_poll_ip", "match_poll_user"}
    assert fired["match_poll_ip"].count(".") == 3
    assert uuid.UUID(fired["match_poll_user"])


@pytest.mark.parametrize(
    "payload",
    [{}, {"url": "https://a.example/", "text": TEXT}, {"text": "short"}, {"link": "x"}],
)
async def test_malformed_intake_is_422(
    match_client: MatchFixture, payload: dict[str, object]
) -> None:
    client, queue, _, headers, _ = match_client

    response = await client.post("/match/jobs", json=payload, headers=headers)

    assert response.status_code == 422
    assert queue.enqueued == []


@pytest.mark.parametrize(
    "url", ["ftp://jobs.example.com/", "https://jobs.example.com:8443/", "https://u:p@a.example/"]
)
async def test_an_unfetchable_url_is_rejected_before_enqueueing(
    match_client: MatchFixture, url: str
) -> None:
    client, queue, _, headers, _ = match_client

    response = await client.post("/match/jobs", json={"url": url}, headers=headers)

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_url"
    assert response.json()["detail"]["message"]
    assert queue.enqueued == []


async def test_intake_requires_authentication(match_client: MatchFixture) -> None:
    client, _, _, _, _ = match_client

    response = await client.post("/match/jobs", json={"text": TEXT})

    assert response.status_code == 401


async def test_a_dead_queue_is_503_and_the_job_is_recorded_as_failed(
    match_client: MatchFixture,
) -> None:
    client, queue, store, headers, _ = match_client
    queue.fail = True

    response = await client.post("/match/jobs", json={"text": TEXT}, headers=headers)

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "unavailable"
    assert response.headers["Retry-After"] == "30"
    [(_, job_id)] = queue.attempted
    record = await store.load(job_id)
    assert record is not None
    assert (record.status, record.error_code) == (JobStatus.FAILED, "queue_unavailable")


async def test_a_broken_store_polls_as_503_unavailable(match_client: MatchFixture) -> None:
    client, _, _, headers, _ = match_client

    class _BrokenStore:
        async def get(self, job_id: str, owner_id: str) -> JobRecord | None:
            raise RedisError("redis is down")

    app.dependency_overrides[get_job_store] = lambda: _BrokenStore()

    response = await client.get(f"/match/jobs/{'A' * 22}", headers=headers)

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "unavailable"
    assert response.headers["Retry-After"] == "30"


async def test_polling_a_queued_job(match_client: MatchFixture) -> None:
    client, _, _, headers, _ = match_client
    job_id = (await client.post("/match/jobs", json={"text": TEXT}, headers=headers)).json()[
        "job_id"
    ]

    response = await client.get(f"/match/jobs/{job_id}", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert (body["job_id"], body["status"], body["posting"], body["error"]) == (
        job_id,
        "queued",
        None,
        None,
    )


async def test_a_finished_job_returns_its_posting(match_client: MatchFixture) -> None:
    client, _, store, headers, _ = match_client
    job_id = (await client.post("/match/jobs", json={"text": TEXT}, headers=headers)).json()[
        "job_id"
    ]
    posting = {
        "title": "Backend Engineer",
        "company": "Acme",
        "responsibilities": [],
        "required": [{"text": "Go", "sensitive": False}],
        "preferred": [],
    }
    await store.mark_done(
        job_id,
        result={"posting": posting, "source": {"kind": "text"}, "input_truncated": True},
        now=time.time(),
    )

    body = (await client.get(f"/match/jobs/{job_id}", headers=headers)).json()

    assert body["status"] == "done"
    assert body["posting"] == posting
    assert body["input_truncated"] is True
    assert body["source_url"] is None


async def test_a_failed_job_explains_itself_and_how_to_recover(match_client: MatchFixture) -> None:
    client, _, store, headers, _ = match_client
    job_id = (
        await client.post(
            "/match/jobs", json={"url": "https://jobs.example.com/1"}, headers=headers
        )
    ).json()["job_id"]
    await store.mark_failed(job_id, error_code="blocked_by_robots", now=time.time())

    body = (await client.get(f"/match/jobs/{job_id}", headers=headers)).json()

    assert body["status"] == "failed"
    assert body["error"]["code"] == "blocked_by_robots"
    assert body["error"]["recovery"] == "paste"
    assert "paste" in body["error"]["message"].lower()


async def test_a_stale_running_job_polls_as_timed_out(match_client: MatchFixture) -> None:
    client, _, store, headers, _ = match_client
    job_id = (await client.post("/match/jobs", json={"text": TEXT}, headers=headers)).json()[
        "job_id"
    ]
    await store.mark_running(
        job_id, stage="extracting", now=time.time() - settings.job_hard_time_limit_seconds - 5
    )

    body = (await client.get(f"/match/jobs/{job_id}", headers=headers)).json()

    assert (body["status"], body["error"]["code"]) == ("failed", "timeout")


async def test_someone_elses_job_is_404(match_client: MatchFixture) -> None:
    client, _, _, headers, _ = match_client
    job_id = (await client.post("/match/jobs", json={"text": TEXT}, headers=headers)).json()[
        "job_id"
    ]
    other = await _login(client, "other@test.dev")

    response = await client.get(f"/match/jobs/{job_id}", headers=other)

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "not_found"


@pytest.mark.parametrize("job_id", ["nope", "A" * 22])
async def test_unknown_or_malformed_ids_are_404(match_client: MatchFixture, job_id: str) -> None:
    client, _, _, headers, _ = match_client

    response = await client.get(f"/match/jobs/{job_id}", headers=headers)

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "not_found"


async def test_an_encoded_slash_in_the_id_never_reaches_the_route(
    match_client: MatchFixture,
) -> None:
    # An encoded slash keeps the path from matching {job_id} at all, so Starlette's own
    # routing 404 fires (plain-string body) before our handler, auth, or rate limit ever run —
    # the same kind of framework-owned exception the contract carves out for 422s.
    client, _, _, headers, _ = match_client

    response = await client.get("/match/jobs/..%2F..%2Fetc", headers=headers)

    assert response.status_code == 404


async def test_a_job_of_another_kind_is_not_served_here(match_client: MatchFixture) -> None:
    client, _, store, headers, _ = match_client
    me = (await client.get("/users/me", headers=headers)).json()["id"]
    record = await store.create("ping", str(me), now=time.time())

    response = await client.get(f"/match/jobs/{record.id}", headers=headers)

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "not_found"


async def test_a_second_intake_while_one_is_active_is_409_with_the_running_job(
    match_client: MatchFixture,
) -> None:
    client, queue, _, headers, _ = match_client
    first = (await client.post("/match/jobs", json={"text": TEXT}, headers=headers)).json()

    response = await client.post("/match/jobs", json={"text": TEXT}, headers=headers)

    assert response.status_code == 409
    body = response.json()
    assert body["detail"]["code"] == "job_in_progress"
    assert body["detail"]["message"]
    assert body["job_id"] == first["job_id"]
    assert len(queue.enqueued) == 1


async def test_another_users_active_intake_does_not_block_mine(match_client: MatchFixture) -> None:
    client, _, _, headers, _ = match_client
    await client.post("/match/jobs", json={"text": TEXT}, headers=headers)
    other = await _login(client, "other@test.dev")

    response = await client.post("/match/jobs", json={"text": TEXT}, headers=other)

    assert response.status_code == 202


@pytest.mark.parametrize("outcome", ["done", "failed"])
async def test_a_finished_intake_frees_the_slot(match_client: MatchFixture, outcome: str) -> None:
    client, queue, store, headers, _ = match_client
    first = (await client.post("/match/jobs", json={"text": TEXT}, headers=headers)).json()
    if outcome == "done":
        await store.mark_done(first["job_id"], result={}, now=time.time())
    else:
        await store.mark_failed(first["job_id"], error_code="expired", now=time.time())

    response = await client.post("/match/jobs", json={"text": TEXT}, headers=headers)

    assert response.status_code == 202
    assert response.json()["job_id"] != first["job_id"]
    assert len(queue.enqueued) == 2


async def test_a_stale_intake_frees_the_slot(match_client: MatchFixture) -> None:
    client, _, store, headers, _ = match_client
    first = (await client.post("/match/jobs", json={"text": TEXT}, headers=headers)).json()
    await store.mark_running(
        first["job_id"],
        stage="extracting",
        now=time.time() - settings.job_hard_time_limit_seconds - 5,
    )

    response = await client.post("/match/jobs", json={"text": TEXT}, headers=headers)

    assert response.status_code == 202
    third = await client.post("/match/jobs", json={"text": TEXT}, headers=headers)
    assert third.status_code == 409
    assert third.json()["job_id"] == response.json()["job_id"]


async def test_a_dead_queue_does_not_hold_the_slot(match_client: MatchFixture) -> None:
    client, queue, _, headers, _ = match_client
    queue.fail = True
    await client.post("/match/jobs", json={"text": TEXT}, headers=headers)
    queue.fail = False

    response = await client.post("/match/jobs", json={"text": TEXT}, headers=headers)

    assert response.status_code == 202


async def test_concurrent_intakes_create_exactly_one_job(
    match_client: MatchFixture, db_session: AsyncSession
) -> None:
    client, queue, _, headers, _ = match_client
    me = (await client.get("/users/me", headers=headers)).json()["id"]
    user = await db_session.get(User, uuid.UUID(me))
    # One shared test session can't serve concurrent auth lookups; the race is in Redis.
    app.dependency_overrides[get_current_user] = lambda: user

    responses = await asyncio.gather(
        *(client.post("/match/jobs", json={"text": TEXT}, headers=headers) for _ in range(5))
    )

    statuses = sorted(response.status_code for response in responses)
    assert statuses == [202, 409, 409, 409, 409]
    [accepted] = [r.json()["job_id"] for r in responses if r.status_code == 202]
    assert {r.json()["job_id"] for r in responses if r.status_code == 409} == {accepted}
    assert queue.enqueued == [("jobs.extract_job", accepted)]
