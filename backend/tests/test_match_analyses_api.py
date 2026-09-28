import asyncio
import json
import time
import uuid
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

import httpx
import pytest
import pytest_asyncio
from documents import make_docx
from fakes import AllowAllLimiter, DenyAllLimiter, FakeTaskQueue
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.analysis_registry import QUEUE_KEY, AnalysisRegistry
from app.core.config import settings
from app.core.db import get_db
from app.core.job_store import JobStateError, JobStatus, JobStore
from app.core.redis import create_redis
from app.deps import get_analysis_registry, get_job_store, get_limiter, get_task_queue
from app.main import app
from app.schemas.match import MatchReport
from app.services.match_failures import describe_failure
from app.services.match_service import CvUpload, MatchService

PASSWORD = "supersecret1"
# Shared with the frontend's report tests, so both sides agree on one realistic report.
GOLDEN_REPORT = Path(__file__).parents[2] / "frontend/lib/__tests__/fixtures/match-report.full.json"
POSTING = {
    "title": "Backend Engineer",
    "company": "Acme",
    "responsibilities": [],
    "required": [{"text": "Go", "sensitive": False}],
    "preferred": [],
}
PDF = b"%PDF-1.4\n" + b"0" * 2048
CV_TEXT = "Backend engineer at Acme building Go services and PostgreSQL schemas. " * 2
# What a browser sends for an empty file input; it also makes httpx send multipart.
NO_FILE = {"cv": ("", b"", "application/octet-stream")}


class Env:
    def __init__(
        self,
        client: httpx.AsyncClient,
        queue: FakeTaskQueue,
        store: JobStore,
        registry: AnalysisRegistry,
        headers: dict[str, str],
        limiter: AllowAllLimiter,
    ) -> None:
        self.client = client
        self.queue = queue
        self.store = store
        self.registry = registry
        self.headers = headers
        self.limiter = limiter

    async def submit(
        self,
        *,
        headers: dict[str, str] | None = None,
        files: dict[str, Any] | None = None,
        form: dict[str, str] | None = None,
        **fields: str,
    ) -> httpx.Response:
        data = {"job": json.dumps(POSTING), "consent": "true", **(form or {}), **fields}
        return await self.client.post(
            "/match/analyses",
            data=data,
            files=files or NO_FILE,
            headers=headers or self.headers,
        )

    async def owner(self, headers: dict[str, str] | None = None) -> str:
        me = await self.client.get("/users/me", headers=headers or self.headers)
        return str(me.json()["id"])

    async def pause(
        self, analysis_id: str, source: str, code: str, reset_at: int | None = None
    ) -> None:
        await self.store.mark_running(analysis_id, stage=f"reading_{source}", now=time.time())
        await self.store.mark_needs_decision(
            analysis_id, failed_source=source, error_code=code, reset_at=reset_at, now=time.time()
        )


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
async def env(
    db_session: AsyncSession, allow_all_limiter: AllowAllLimiter, redis_client: Redis
) -> AsyncGenerator[Env]:
    async def override_get_db() -> AsyncGenerator[AsyncSession]:
        yield db_session
        await db_session.commit()

    queue = FakeTaskQueue()
    store = JobStore(redis_client, ttl_seconds=settings.job_ttl_seconds)
    registry = AnalysisRegistry(redis_client, ttl_seconds=settings.job_ttl_seconds)
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_limiter] = lambda: allow_all_limiter
    app.dependency_overrides[get_task_queue] = lambda: queue
    app.dependency_overrides[get_job_store] = lambda: store
    app.dependency_overrides[get_analysis_registry] = lambda: registry
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://test") as client:
        headers = await _login(client, f"{uuid.uuid4().hex[:10]}@test.dev")
        allow_all_limiter.calls.clear()
        yield Env(client, queue, store, registry, headers, allow_all_limiter)
    app.dependency_overrides.clear()


def detail_code(response: httpx.Response) -> str:
    return str(response.json()["detail"]["code"])


# --- submit ---------------------------------------------------------------------------


async def test_a_github_only_analysis_is_accepted_and_enqueued(env: Env) -> None:
    response = await env.submit(github_url="https://github.com/jane")

    assert response.status_code == 202
    analysis_id = response.json()["analysis_id"]
    assert env.queue.enqueued == [("jobs.run_analysis", analysis_id)]
    record = await env.store.load(analysis_id)
    assert record is not None
    assert (record.kind, record.status) == ("match_analysis", JobStatus.QUEUED)
    stored = json.loads(await env.store.read_blob(analysis_id, "analysis_input") or b"{}")
    assert stored == {
        "posting": POSTING,
        "github_url": "https://github.com/jane",
        "cv_provided": False,
    }
    assert [name for name, _ in env.limiter.calls] == ["match_analysis_user"]


async def test_an_uploaded_cv_is_kept_in_redis_for_fifteen_minutes_only(
    env: Env, redis_client: Redis
) -> None:
    response = await env.submit(files={"cv": ("cv.pdf", PDF, "application/pdf")})

    assert response.status_code == 202
    analysis_id = response.json()["analysis_id"]
    key = f"job:{analysis_id}:blob:cv_file"
    assert await redis_client.get(key) == PDF
    assert 0 < await redis_client.ttl(key) <= settings.match_cv_ttl_seconds
    assert 0 < await redis_client.ttl(f"job:{analysis_id}") <= settings.job_ttl_seconds


async def test_pasted_cv_text_is_accepted(env: Env) -> None:
    response = await env.submit(cv_text=CV_TEXT)

    assert response.status_code == 202
    analysis_id = response.json()["analysis_id"]
    assert await env.store.read_blob(analysis_id, "cv_text") == CV_TEXT.strip().encode()


async def test_an_empty_file_part_from_the_browser_counts_as_no_file(env: Env) -> None:
    response = await env.submit(files=NO_FILE, github_url="https://github.com/jane")

    assert response.status_code == 202


@pytest.mark.parametrize(
    ("fields", "files", "code"),
    [
        ({"consent": "yes", "github_url": "https://github.com/jane"}, None, "consent_required"),
        ({"job": "{not json", "github_url": "https://github.com/jane"}, None, "invalid_job"),
        (
            {"job": json.dumps({"title": ""}), "github_url": "https://github.com/jane"},
            None,
            "invalid_job",
        ),
        ({}, None, "no_candidate_source"),
        ({"cv_text": CV_TEXT}, {"cv": ("cv.pdf", PDF, "application/pdf")}, "cv_and_cv_text"),
        ({"github_url": "https://github.com/jane/repo"}, None, "invalid_github_url"),
        ({"github_url": "http://github.com/jane"}, None, "invalid_github_url"),
    ],
    ids=[
        "consent",
        "job-not-json",
        "job-invalid",
        "no-source",
        "cv-and-text",
        "repo-url",
        "http-url",
    ],
)
async def test_invalid_submissions_are_422_with_a_code_and_never_enqueued(
    env: Env, fields: dict[str, str], files: dict[str, Any] | None, code: str
) -> None:
    response = await env.submit(files=files, form=fields)

    assert response.status_code == 422
    assert detail_code(response) == code
    assert response.json()["detail"]["message"]
    assert env.queue.attempted == []


async def test_cv_text_outside_its_length_limits_is_a_validation_error(env: Env) -> None:
    response = await env.submit(cv_text="too short")

    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)


async def test_a_form_that_is_not_multipart_is_a_validation_error(env: Env) -> None:
    response = await env.client.post(
        "/match/analyses", json={"job": POSTING, "consent": "true"}, headers=env.headers
    )

    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)


async def test_a_file_that_is_neither_pdf_nor_docx_is_415(env: Env) -> None:
    response = await env.submit(files={"cv": ("cv.pdf", b"MZ\x90\x00 an exe", "application/pdf")})

    assert response.status_code == 415
    assert detail_code(response) == "unsupported_type"


async def test_an_upload_over_the_limit_is_413_and_stores_nothing(
    env: Env, redis_client: Redis
) -> None:
    too_big = b"%PDF-" + b"0" * settings.max_upload_bytes
    before = set(await redis_client.keys("job:*"))

    response = await env.submit(files={"cv": ("cv.pdf", too_big, "application/pdf")})

    assert response.status_code == 413
    assert detail_code(response) == "file_too_large"
    assert env.queue.attempted == []
    assert set(await redis_client.keys("job:*")) == before
    assert await env.registry.holder(await env.owner()) is None


async def test_a_declared_body_over_the_limit_is_413_before_the_body_is_read(env: Env) -> None:
    async def endless() -> AsyncGenerator[bytes]:
        raise AssertionError("the body was read")
        yield b""  # pragma: no cover - makes this an async generator

    response = await env.client.post(
        "/match/analyses",
        content=endless(),
        headers={
            **env.headers,
            "content-type": "multipart/form-data; boundary=x",
            "content-length": str(settings.max_upload_bytes * 10),
        },
    )

    assert response.status_code == 413


async def test_an_upload_is_never_written_to_disk(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    import tempfile

    def refuse(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("a temp file was created on disk")

    for name in ("TemporaryFile", "NamedTemporaryFile", "mkstemp", "mkdtemp"):
        monkeypatch.setattr(tempfile, name, refuse)
    big_pdf = b"%PDF-1.4\n" + b"0" * (settings.max_upload_bytes - 64)

    response = await env.submit(files={"cv": ("cv.pdf", big_pdf, "application/pdf")})

    assert response.status_code == 202


async def test_a_second_active_analysis_is_409_and_names_the_running_one(env: Env) -> None:
    first = (await env.submit(github_url="https://github.com/jane")).json()["analysis_id"]

    response = await env.submit(cv_text=CV_TEXT)

    assert response.status_code == 409
    body = response.json()
    assert (body["detail"]["code"], body["analysis_id"]) == ("analysis_in_progress", first)
    assert env.queue.enqueued == [("jobs.run_analysis", first)]


async def test_a_paused_analysis_still_blocks_a_new_one(env: Env) -> None:
    first = (await env.submit(github_url="https://github.com/jane")).json()["analysis_id"]
    await env.pause(first, "github", "github_unavailable")

    response = await env.submit(github_url="https://github.com/jane")

    assert response.status_code == 409


async def test_a_refused_second_submission_stores_no_cv(env: Env, redis_client: Redis) -> None:
    await env.submit(github_url="https://github.com/jane")
    before = set(await redis_client.keys("job:*:blob:cv_text"))

    await env.submit(cv_text=CV_TEXT)

    assert set(await redis_client.keys("job:*:blob:cv_text")) == before


@pytest.mark.parametrize("finish", ["done", "failed", "stale"])
async def test_a_finished_analysis_releases_the_lock_by_itself(env: Env, finish: str) -> None:
    first = (await env.submit(github_url="https://github.com/jane")).json()["analysis_id"]
    if finish == "done":
        await env.store.mark_done(first, result={"report": None}, now=time.time())
    elif finish == "failed":
        await env.store.mark_failed(first, error_code="ai_unavailable", now=time.time())
    else:
        stale = time.time() - settings.match_analysis_hard_time_limit_seconds - 5
        await env.store.mark_running(first, stage="assessing", now=stale)

    response = await env.submit(github_url="https://github.com/jane")

    assert response.status_code == 202


async def test_locks_are_per_user(env: Env) -> None:
    await env.submit(github_url="https://github.com/jane")
    other = await _login(env.client, f"{uuid.uuid4().hex[:10]}@test.dev")

    response = await env.submit(headers=other, github_url="https://github.com/jane")

    assert response.status_code == 202


async def test_a_dead_queue_is_503_fails_the_record_and_frees_the_lock(env: Env) -> None:
    env.queue.fail = True

    response = await env.submit(github_url="https://github.com/jane")

    assert response.status_code == 503
    [(_, analysis_id)] = env.queue.attempted
    record = await env.store.load(analysis_id)
    assert record is not None and record.error_code == "queue_unavailable"
    assert await env.registry.holder(await env.owner()) is None


async def test_submitting_requires_authentication(env: Env) -> None:
    response = await env.client.post("/match/analyses", data={"consent": "true"})

    assert response.status_code == 401


# --- poll -----------------------------------------------------------------------------


async def test_a_queued_analysis_reports_its_queue_position(env: Env, redis_client: Redis) -> None:
    await redis_client.delete(QUEUE_KEY)
    other = await _login(env.client, f"{uuid.uuid4().hex[:10]}@test.dev")
    first = (await env.submit(headers=other, github_url="https://github.com/jane")).json()[
        "analysis_id"
    ]
    mine = (await env.submit(github_url="https://github.com/jane")).json()["analysis_id"]

    body = (await env.client.get(f"/match/analyses/{mine}", headers=env.headers)).json()

    assert (body["status"], body["stage"], body["queue_position"]) == ("queued", None, 1)
    await env.store.mark_running(first, stage="reading_github", now=time.time())
    body = (await env.client.get(f"/match/analyses/{mine}", headers=env.headers)).json()
    assert body["queue_position"] == 0


async def test_a_running_analysis_has_no_queue_position(env: Env) -> None:
    analysis_id = (await env.submit(github_url="https://github.com/jane")).json()["analysis_id"]
    await env.store.mark_running(analysis_id, stage="assessing", now=time.time())

    body = (await env.client.get(f"/match/analyses/{analysis_id}", headers=env.headers)).json()

    assert (body["status"], body["stage"], body["queue_position"]) == ("running", "assessing", None)


async def test_a_paused_analysis_explains_the_decision_with_the_reset_time(env: Env) -> None:
    analysis_id = (await env.submit(github_url="https://github.com/jane")).json()["analysis_id"]
    await env.pause(analysis_id, "github", "github_rate_limited", reset_at=1790000000)

    body = (await env.client.get(f"/match/analyses/{analysis_id}", headers=env.headers)).json()

    assert body["status"] == "needs_decision"
    assert body["error"] is None
    assert body["decision"]["failed_source"] == "github"
    assert body["decision"]["error"]["code"] == "github_rate_limited"
    assert "UTC" in body["decision"]["error"]["message"]


async def test_a_finished_analysis_returns_its_report(env: Env) -> None:
    from app.services.analysis_sources import CvSource, GitHubSource, SourcesState
    from app.services.match_report import refusal_report

    analysis_id = (await env.submit(github_url="https://github.com/jane")).json()["analysis_id"]
    report = refusal_report(
        ["insufficient_evidence"],
        sources=SourcesState(
            cv=CvSource(status="not_provided"), github=GitHubSource(status="read")
        ),
        model="ollama/qwen3:8b",
    )
    await env.store.mark_done(
        analysis_id, result={"report": report.model_dump(mode="json")}, now=time.time()
    )

    body = (await env.client.get(f"/match/analyses/{analysis_id}", headers=env.headers)).json()

    assert body["status"] == "done"
    assert body["report"] == report.model_dump(mode="json")
    assert body["report"]["score"] is None


async def test_a_failed_analysis_explains_itself(env: Env) -> None:
    analysis_id = (await env.submit(github_url="https://github.com/jane")).json()["analysis_id"]
    await env.store.mark_failed(analysis_id, error_code="ai_invalid_output", now=time.time())

    body = (await env.client.get(f"/match/analyses/{analysis_id}", headers=env.headers)).json()

    assert (body["status"], body["error"]["code"], body["decision"]) == (
        "failed",
        "ai_invalid_output",
        None,
    )


async def test_a_stale_running_analysis_polls_as_timed_out(env: Env) -> None:
    analysis_id = (await env.submit(github_url="https://github.com/jane")).json()["analysis_id"]
    stale = time.time() - settings.match_analysis_hard_time_limit_seconds - 5
    await env.store.mark_running(analysis_id, stage="assessing", now=stale)

    body = (await env.client.get(f"/match/analyses/{analysis_id}", headers=env.headers)).json()

    assert (body["status"], body["error"]["code"]) == ("failed", "timeout")


async def test_a_long_running_analysis_is_not_stale_under_the_job_limit(env: Env) -> None:
    analysis_id = (await env.submit(github_url="https://github.com/jane")).json()["analysis_id"]
    await env.store.mark_running(
        analysis_id, stage="assessing", now=time.time() - settings.job_hard_time_limit_seconds - 5
    )

    body = (await env.client.get(f"/match/analyses/{analysis_id}", headers=env.headers)).json()

    assert body["status"] == "running"


async def test_someone_elses_analysis_is_404(env: Env) -> None:
    analysis_id = (await env.submit(github_url="https://github.com/jane")).json()["analysis_id"]
    other = await _login(env.client, f"{uuid.uuid4().hex[:10]}@test.dev")

    response = await env.client.get(f"/match/analyses/{analysis_id}", headers=other)

    assert response.status_code == 404
    assert detail_code(response) == "analysis_not_found"


async def test_a_job_intake_id_is_not_an_analysis(env: Env) -> None:
    record = await env.store.create("job_intake", await env.owner(), now=time.time())

    response = await env.client.get(f"/match/analyses/{record.id}", headers=env.headers)

    assert response.status_code == 404


# --- continue / retry -----------------------------------------------------------------


async def test_continue_requeues_a_paused_analysis(env: Env) -> None:
    analysis_id = (await env.submit(cv_text=CV_TEXT, github_url="https://github.com/jane")).json()[
        "analysis_id"
    ]
    await env.pause(analysis_id, "cv", "scanned_pdf_suspected")

    response = await env.client.post(f"/match/analyses/{analysis_id}/continue", headers=env.headers)

    assert response.status_code == 202
    assert response.json() == {"analysis_id": analysis_id}
    record = await env.store.load(analysis_id)
    assert record is not None
    assert (record.status, record.resume) == (JobStatus.QUEUED, "continue")
    assert env.queue.enqueued[-1] == ("jobs.run_analysis", analysis_id)
    assert [name for name, _ in env.limiter.calls][-1] == "match_poll_user"


async def test_a_resume_near_the_end_of_the_ttl_gets_time_to_queue_and_run(
    env: Env, redis_client: Redis
) -> None:
    analysis_id = (await env.submit(cv_text=CV_TEXT, github_url="https://github.com/jane")).json()[
        "analysis_id"
    ]
    await env.pause(analysis_id, "cv", "scanned_pdf_suspected")
    await env.store.attach_blob(analysis_id, "sources", b"{}")
    for key in (
        f"job:{analysis_id}",
        *(f"job:{analysis_id}:blob:{n}" for n in ("analysis_input", "sources")),
    ):
        await redis_client.expire(key, 5)

    response = await env.client.post(f"/match/analyses/{analysis_id}/continue", headers=env.headers)

    assert response.status_code == 202
    budget = settings.job_queue_stale_seconds + settings.match_analysis_hard_time_limit_seconds
    for key in (
        f"job:{analysis_id}",
        f"job:{analysis_id}:blob:analysis_input",
        f"job:{analysis_id}:blob:sources",
    ):
        assert await redis_client.ttl(key) >= budget - 5, key


async def test_continue_on_an_analysis_that_is_not_paused_is_409(env: Env) -> None:
    analysis_id = (await env.submit(github_url="https://github.com/jane")).json()["analysis_id"]

    response = await env.client.post(f"/match/analyses/{analysis_id}/continue", headers=env.headers)

    assert response.status_code == 409
    assert detail_code(response) == "not_awaiting_decision"


async def test_a_github_retry_needs_no_body(env: Env) -> None:
    analysis_id = (await env.submit(cv_text=CV_TEXT, github_url="https://github.com/jane")).json()[
        "analysis_id"
    ]
    await env.pause(analysis_id, "github", "github_unavailable")

    response = await env.client.post(f"/match/analyses/{analysis_id}/retry", headers=env.headers)

    assert response.status_code == 202
    record = await env.store.load(analysis_id)
    assert record is not None and record.resume == "retry"
    assert [name for name, _ in env.limiter.calls][-1] == "match_analysis_user"


async def test_a_cv_retry_needs_the_cv_again(env: Env) -> None:
    analysis_id = (
        await env.submit(
            files={"cv": ("cv.pdf", PDF, "application/pdf")}, github_url="https://github.com/jane"
        )
    ).json()["analysis_id"]
    await env.pause(analysis_id, "cv", "scanned_pdf_suspected")

    missing = await env.client.post(f"/match/analyses/{analysis_id}/retry", headers=env.headers)
    assert missing.status_code == 422
    assert detail_code(missing) == "no_candidate_source"

    response = await env.client.post(
        f"/match/analyses/{analysis_id}/retry",
        data={"cv_text": CV_TEXT},
        files=NO_FILE,
        headers=env.headers,
    )
    assert response.status_code == 202
    assert await env.store.read_blob(analysis_id, "cv_text") == CV_TEXT.strip().encode()


async def test_a_cv_retry_checks_the_new_file_like_a_submission(env: Env) -> None:
    analysis_id = (await env.submit(cv_text=CV_TEXT, github_url="https://github.com/jane")).json()[
        "analysis_id"
    ]
    await env.pause(analysis_id, "cv", "scanned_pdf_suspected")

    response = await env.client.post(
        f"/match/analyses/{analysis_id}/retry",
        files={"cv": ("cv.pdf", b"MZ not a pdf", "application/pdf")},
        headers=env.headers,
    )

    assert response.status_code == 415


async def test_a_retry_that_loses_the_race_writes_no_cv(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    analysis_id = (
        await env.submit(
            files={"cv": ("cv.pdf", PDF, "application/pdf")}, github_url="https://github.com/jane"
        )
    ).json()["analysis_id"]
    await env.pause(analysis_id, "cv", "scanned_pdf_suspected")

    async def lost_race(*args: Any, **kwargs: Any) -> None:
        # Another request continued the analysis between the status check and the write.
        raise JobStateError("changed")

    monkeypatch.setattr(env.store, "resume", lost_race)
    response = await env.client.post(
        f"/match/analyses/{analysis_id}/retry",
        data={"cv_text": CV_TEXT},
        files=NO_FILE,
        headers=env.headers,
    )

    assert response.status_code == 409
    assert await env.store.read_blob(analysis_id, "cv_text") is None


async def test_two_concurrent_cv_retries_keep_the_winners_cv(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    analysis_id = (
        await env.submit(
            files={"cv": ("cv.pdf", PDF, "application/pdf")}, github_url="https://github.com/jane"
        )
    ).json()["analysis_id"]
    await env.pause(analysis_id, "cv", "scanned_pdf_suspected")
    real_resume = env.store.resume
    arrived = 0
    both_here = asyncio.Event()

    async def together(*args: Any, **kwargs: Any) -> Any:
        # Both requests have passed the status check before either writes: the real race.
        nonlocal arrived
        arrived += 1
        if arrived == 2:
            both_here.set()
        await both_here.wait()
        return await real_resume(*args, **kwargs)

    monkeypatch.setattr(env.store, "resume", together)
    # Straight to the service: two HTTP requests would share the test's one DB session.
    service = MatchService(env.store, env.queue, env.registry)
    owner = await env.owner()
    texts = [b"first retry cv text", b"second retry cv text"]
    outcomes = await asyncio.gather(
        *(
            service.retry_analysis(owner, analysis_id, CvUpload("text", text), now=time.time())
            for text in texts
        ),
        return_exceptions=True,
    )

    assert sorted(type(outcome).__name__ for outcome in outcomes) == [
        "NotAwaitingDecisionError",
        "str",
    ]
    winner = texts[[isinstance(outcome, str) for outcome in outcomes].index(True)]
    assert await env.store.read_blob(analysis_id, "cv_text") == winner


async def test_continue_on_someone_elses_analysis_is_404(env: Env) -> None:
    analysis_id = (await env.submit(github_url="https://github.com/jane")).json()["analysis_id"]
    await env.pause(analysis_id, "github", "github_unavailable")
    other = await _login(env.client, f"{uuid.uuid4().hex[:10]}@test.dev")

    response = await env.client.post(f"/match/analyses/{analysis_id}/continue", headers=other)

    assert response.status_code == 404


async def test_a_full_queue_refuses_a_new_analysis_with_queue_full(
    env: Env, monkeypatch: pytest.MonkeyPatch, redis_client: Redis
) -> None:
    await redis_client.delete(QUEUE_KEY)
    monkeypatch.setattr(settings, "match_max_queued_analyses", 1)
    other = await _login(env.client, f"{uuid.uuid4().hex[:10]}@test.dev")
    await env.submit(headers=other, github_url="https://github.com/jane")

    response = await env.submit(github_url="https://github.com/jane")

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "queue_full"
    assert response.headers["Retry-After"]
    assert len(env.queue.enqueued) == 1
    assert await env.registry.holder(await env.owner()) is None


async def test_analyses_that_left_the_queue_do_not_count_towards_the_cap(
    env: Env, monkeypatch: pytest.MonkeyPatch, redis_client: Redis
) -> None:
    await redis_client.delete(QUEUE_KEY)
    monkeypatch.setattr(settings, "match_max_queued_analyses", 1)
    other = await _login(env.client, f"{uuid.uuid4().hex[:10]}@test.dev")
    first = (await env.submit(headers=other, github_url="https://github.com/jane")).json()
    await env.store.mark_running(first["analysis_id"], stage="assessing", now=time.time())

    response = await env.submit(github_url="https://github.com/jane")

    assert response.status_code == 202


@pytest.mark.parametrize("state", ["paused", "queued"])
async def test_discarding_an_analysis_frees_the_lock_and_its_inputs(
    env: Env, redis_client: Redis, state: str
) -> None:
    analysis_id = (await env.submit(cv_text=CV_TEXT, github_url="https://github.com/jane")).json()[
        "analysis_id"
    ]
    if state == "paused":
        await env.pause(analysis_id, "cv", "scanned_pdf_suspected")

    response = await env.client.post(f"/match/analyses/{analysis_id}/discard", headers=env.headers)

    assert response.status_code == 200
    assert response.json() == {"analysis_id": analysis_id}
    body = (await env.client.get(f"/match/analyses/{analysis_id}", headers=env.headers)).json()
    assert (body["status"], body["error"]["code"]) == ("failed", "analysis_discarded")
    assert await redis_client.keys(f"job:{analysis_id}:blob:*") == []
    assert (await env.submit(github_url="https://github.com/jane")).status_code == 202


async def test_a_running_analysis_cannot_be_discarded(env: Env) -> None:
    analysis_id = (await env.submit(github_url="https://github.com/jane")).json()["analysis_id"]
    await env.store.mark_running(analysis_id, stage="assessing", now=time.time())

    response = await env.client.post(f"/match/analyses/{analysis_id}/discard", headers=env.headers)

    assert response.status_code == 409
    assert detail_code(response) == "analysis_running"


async def test_discarding_someone_elses_analysis_is_404(env: Env) -> None:
    analysis_id = (await env.submit(github_url="https://github.com/jane")).json()["analysis_id"]
    other = await _login(env.client, f"{uuid.uuid4().hex[:10]}@test.dev")

    response = await env.client.post(f"/match/analyses/{analysis_id}/discard", headers=other)

    assert response.status_code == 404
    record = await env.store.load(analysis_id)
    assert record is not None and record.status is JobStatus.QUEUED


async def test_a_github_retry_can_carry_a_corrected_url(env: Env) -> None:
    analysis_id = (await env.submit(cv_text=CV_TEXT, github_url="https://github.com/jane")).json()[
        "analysis_id"
    ]
    await env.pause(analysis_id, "github", "github_user_not_found")

    response = await env.client.post(
        f"/match/analyses/{analysis_id}/retry",
        data={"github_url": "https://github.com/jane-doe/"},
        files=NO_FILE,
        headers=env.headers,
    )

    assert response.status_code == 202
    assert await env.store.read_blob(analysis_id, "github_url") == b"https://github.com/jane-doe/"


@pytest.mark.parametrize(
    ("source", "url"),
    [
        ("github", "https://github.com/jane/repo"),
        ("github", "http://github.com/jane"),
        ("cv", "https://github.com/jane"),
    ],
)
async def test_a_corrected_url_is_validated_like_the_submit_field(
    env: Env, source: str, url: str
) -> None:
    analysis_id = (await env.submit(cv_text=CV_TEXT, github_url="https://github.com/jane")).json()[
        "analysis_id"
    ]
    await env.pause(analysis_id, source, "github_user_not_found")

    response = await env.client.post(
        f"/match/analyses/{analysis_id}/retry",
        data={"github_url": url, **({"cv_text": CV_TEXT} if source == "cv" else {})},
        files=NO_FILE,
        headers=env.headers,
    )

    assert response.status_code == 422
    assert detail_code(response) == "invalid_github_url"
    record = await env.store.load(analysis_id)
    assert record is not None and record.status is JobStatus.NEEDS_DECISION


async def test_a_macro_docx_is_415_unsafe_docx(env: Env) -> None:
    macro = make_docx("Backend engineer", extra={"word/vbaProject.bin": b"\x00" * 64})

    response = await env.submit(files={"cv": ("cv.docx", macro, "application/octet-stream")})

    assert response.status_code == 415
    assert detail_code(response) == "unsafe_docx"
    assert response.json()["detail"]["message"] == describe_failure("unsafe_docx").message


async def test_an_unreadable_stored_report_polls_as_a_coded_failure(
    env: Env, caplog: pytest.LogCaptureFixture
) -> None:
    analysis_id = (await env.submit(github_url="https://github.com/jane")).json()["analysis_id"]
    await env.store.mark_done(
        analysis_id, result={"report": {"score": 70, "leaked": "Tyrell secret"}}, now=time.time()
    )

    with caplog.at_level("WARNING"):
        response = await env.client.get(f"/match/analyses/{analysis_id}", headers=env.headers)

    assert response.status_code == 200
    body = response.json()
    assert (body["status"], body["error"]["code"], body["report"]) == (
        "failed",
        "internal_error",
        None,
    )
    assert "ValidationError" in caplog.text
    assert "Tyrell secret" not in caplog.text


async def test_a_resumed_analysis_shows_no_stage_until_it_runs(env: Env) -> None:
    analysis_id = (await env.submit(cv_text=CV_TEXT, github_url="https://github.com/jane")).json()[
        "analysis_id"
    ]
    await env.pause(analysis_id, "cv", "scanned_pdf_suspected")

    await env.client.post(f"/match/analyses/{analysis_id}/continue", headers=env.headers)

    body = (await env.client.get(f"/match/analyses/{analysis_id}", headers=env.headers)).json()
    assert (body["status"], body["stage"]) == ("queued", None)


@pytest.mark.parametrize(
    "fields",
    [
        {"status": "done", "report": None},
        {"status": "needs_decision", "decision": None},
        {"status": "failed", "error": None},
        {"status": "running", "queue_position": 2},
        {"status": "running", "stage": "reading"},
    ],
    ids=[
        "done-no-report",
        "paused-no-decision",
        "failed-no-error",
        "position-not-queued",
        "intake-stage",
    ],
)
def test_a_status_response_that_breaks_the_contract_is_rejected(fields: dict[str, Any]) -> None:
    from pydantic import ValidationError

    from app.schemas.match import AnalysisStatusResponse

    base: dict[str, Any] = {
        "analysis_id": "A" * 22,
        "status": "queued",
        "stage": None,
        "queue_position": 0,
        "error": None,
        "decision": None,
        "report": None,
    }
    with pytest.raises(ValidationError):
        AnalysisStatusResponse.model_validate({**base, "queue_position": None, **fields})


async def test_the_upload_limits_are_published_without_auth(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "max_upload_mb", 12)

    response = await env.client.get("/match/config")

    assert response.status_code == 200
    assert response.json() == {
        "max_upload_bytes": 12 * 1024 * 1024,
        "cv_text_min_chars": 50,
        "cv_text_max_chars": 40_000,
    }
    assert [name for name, _ in env.limiter.calls] == ["match_poll_ip"]


def _paused_by_a(kind: str) -> dict[str, Any]:
    if kind == "text":
        return {"data": {"cv_text": CV_TEXT}, "files": NO_FILE}
    return {"files": {"cv": ("cv.pdf", PDF, "application/pdf")}}


@pytest.mark.parametrize("kind", ["text", "file"])
async def test_someone_elses_cv_retry_is_404_and_writes_nothing(
    env: Env, redis_client: Redis, kind: str
) -> None:
    analysis_id = (await env.submit(cv_text=CV_TEXT, github_url="https://github.com/jane")).json()[
        "analysis_id"
    ]
    await env.pause(analysis_id, "cv", "scanned_pdf_suspected")
    enqueued = list(env.queue.enqueued)
    other = await _login(env.client, f"{uuid.uuid4().hex[:10]}@test.dev")
    before = {key: await redis_client.get(key) for key in await redis_client.keys("job:*")}

    response = await env.client.post(
        f"/match/analyses/{analysis_id}/retry", headers=other, **_paused_by_a(kind)
    )

    assert response.status_code == 404
    after = {key: await redis_client.get(key) for key in await redis_client.keys("job:*")}
    assert after == before
    assert env.queue.enqueued == enqueued
    record = await env.store.load(analysis_id)
    assert record is not None and record.status is JobStatus.NEEDS_DECISION


@pytest.mark.parametrize(
    ("method", "suffix"),
    [("GET", ""), ("POST", "/continue"), ("POST", "/retry"), ("POST", "/discard")],
)
async def test_every_analysis_route_requires_authentication(
    env: Env, method: str, suffix: str
) -> None:
    response = await env.client.request(method, f"/match/analyses/{'A' * 22}{suffix}")

    assert response.status_code == 401


async def _never_read() -> AsyncGenerator[bytes]:
    raise AssertionError("the body was read")
    yield b""  # pragma: no cover - makes this an async generator


async def test_an_unauthenticated_upload_is_refused_before_its_body_is_read(env: Env) -> None:
    response = await env.client.post(
        "/match/analyses",
        content=_never_read(),
        headers={"content-type": "multipart/form-data; boundary=x"},
    )

    assert response.status_code == 401


async def test_a_rate_limited_upload_is_refused_before_its_body_is_read(env: Env) -> None:
    app.dependency_overrides[get_limiter] = DenyAllLimiter

    response = await env.client.post(
        "/match/analyses",
        content=_never_read(),
        headers={**env.headers, "content-type": "multipart/form-data; boundary=x"},
    )

    assert response.status_code == 429
    assert response.headers["Retry-After"]


async def test_the_golden_full_report_round_trips_through_the_api(env: Env) -> None:
    golden = json.loads(GOLDEN_REPORT.read_text())
    MatchReport.model_validate(golden)
    analysis_id = (await env.submit(github_url="https://github.com/jane")).json()["analysis_id"]
    await env.store.mark_done(analysis_id, result={"report": golden}, now=time.time())

    body = (await env.client.get(f"/match/analyses/{analysis_id}", headers=env.headers)).json()

    assert body["status"] == "done"
    assert body["report"] == golden
    statuses = {requirement["status"] for requirement in golden["requirements"]}
    assert statuses == {"demonstrated", "partial", "unmet", "not_demonstrated", "not_assessed"}
    assert golden["rewrites"] and golden["recommendations"]["immediate"]
