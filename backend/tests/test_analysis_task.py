import asyncio
import json
import time
import uuid
from typing import Any

import pytest
from documents import CV_LINE, make_pdf, text_page
from fakes import NearEmbedder, ScriptedGenerator

from app.core.config import settings
from app.core.job_store import JobRecord, JobStatus, JobStore
from app.core.redis import create_redis
from app.integrations.errors import GitHubError, GitHubFailure
from app.integrations.github import GitHubProfile, GitHubRepo, GitHubSnapshot
from app.schemas.match import AnalysisInput
from app.workers import tasks
from app.workers.celery_app import celery_app

CV_TEXT = f"{CV_LINE}\n" * 5
POSTING = {
    "title": "Backend Engineer",
    "company": "Acme",
    "responsibilities": [],
    "required": [{"text": "Go", "sensitive": False}, {"text": "PostgreSQL", "sensitive": False}],
    "preferred": [{"text": "Kafka", "sensitive": False}],
}
CV_REPLY = json.dumps(
    {
        "is_cv": True,
        "items": [
            {"kind": "work", "section_label": "Experience · Acme", "text": CV_LINE, "links": []}
        ],
    }
)
ASSESS_REPLY = json.dumps(
    {
        "assessments": [
            {
                "ref": "R1",
                "status": "demonstrated",
                "evidence_ids": ["gh:repo:ledger"],
                "rationale": "A Go ledger.",
            },
            {"ref": "R2", "status": "not_demonstrated", "evidence_ids": [], "rationale": "None."},
            {"ref": "R3", "status": "not_demonstrated", "evidence_ids": [], "rationale": "None."},
        ]
    }
)
ADVICE_REPLY = json.dumps({"immediate": [], "longer_term": [], "rewrites": []})


class Fetcher:
    def __init__(self, *, error: GitHubError | None = None) -> None:
        self.error = error
        self.calls = 0
        self.usernames: list[str] = []

    async def fetch(self, username: str) -> GitHubSnapshot:
        self.calls += 1
        self.usernames.append(username)
        if self.error is not None:
            raise self.error
        repos = [
            GitHubRepo(
                name=name,
                url=f"https://github.com/{username}/{name}",
                description=f"{name} written in Go",
                languages={"Go": 1},
                topics=[],
                stars=0,
                pushed_at=None,
                readme=None,
            )
            for name in ("ledger", "queue", "cache")
        ]
        return GitHubSnapshot(
            profile=GitHubProfile(login=username, bio="Backend engineer", public_repos=9),
            repos=repos,
            candidate_repos=3,
            fetched_at=time.time(),
        )


class Models:
    def __init__(self, evidence: list[str], assess: list[str], recommend: list[str]) -> None:
        self.generators = tasks.AnalysisGenerators(
            evidence=ScriptedGenerator(evidence),
            assess=ScriptedGenerator(assess),
            recommend=ScriptedGenerator(recommend),
        )

    def __call__(self) -> tasks.AnalysisGenerators:
        return self.generators


@pytest.fixture
def fetcher(monkeypatch: pytest.MonkeyPatch) -> Fetcher:
    fake = Fetcher()
    monkeypatch.setattr(tasks, "GitHubClient", lambda **_: fake)
    monkeypatch.setattr(tasks, "BgeEmbedder", NearEmbedder)
    return fake


def use_models(monkeypatch: pytest.MonkeyPatch, **replies: list[str]) -> Models:
    models = Models(
        replies.get("evidence", []), replies.get("assess", []), replies.get("recommend", [])
    )
    monkeypatch.setattr(tasks, "build_analysis_generators", models)
    return models


def in_store(work: Any) -> Any:
    async def run() -> Any:
        redis = create_redis()
        try:
            return await work(JobStore(redis, ttl_seconds=settings.job_ttl_seconds))
        finally:
            await redis.aclose()

    return asyncio.run(run())


def submit(*, github: bool = True, cv_text: str | None = None, cv_file: bytes | None = None) -> str:
    request = AnalysisInput.model_validate(
        {
            "posting": POSTING,
            # A fresh user per test: load_github caches public profiles in Redis for an hour.
            "github_url": f"https://github.com/u{uuid.uuid4().hex[:12]}" if github else None,
            "cv_provided": bool(cv_text or cv_file),
        }
    )

    async def create(store: JobStore) -> str:
        record = await store.create("match_analysis", "owner", now=time.time())
        await store.attach_blob(record.id, "analysis_input", request.model_dump_json().encode())
        if cv_text is not None:
            await store.put_blob(record.id, "cv_text", cv_text.encode(), ttl_seconds=60)
        if cv_file is not None:
            await store.put_blob(record.id, "cv_file", cv_file, ttl_seconds=60)
        return record.id

    return in_store(create)  # type: ignore[no-any-return]


def load(job_id: str) -> JobRecord:
    record = in_store(lambda store: store.load(job_id))
    assert record is not None
    return record  # type: ignore[no-any-return]


def blob(job_id: str, name: str) -> bytes | None:
    return in_store(lambda store: store.read_blob(job_id, name))  # type: ignore[no-any-return]


def resume(job_id: str, directive: str) -> None:
    in_store(lambda store: store.resume(job_id, "owner", resume=directive, now=time.time()))


def run(job_id: str) -> None:
    tasks.run_analysis_task.apply(args=(job_id,))


def test_a_github_only_analysis_finishes_with_a_report_and_forgets_its_inputs(
    monkeypatch: pytest.MonkeyPatch, fetcher: Fetcher
) -> None:
    use_models(monkeypatch, assess=[ASSESS_REPLY], recommend=[ADVICE_REPLY])
    job_id = submit()

    run(job_id)

    record = load(job_id)
    assert record.status is JobStatus.DONE, record.error_code
    assert record.stage == "recommending"
    assert record.result is not None
    report = record.result["report"]
    assert report["score"] is not None
    assert report["coverage"]["github"]["status"] == "read"
    assert report["requirements"][0]["evidence"][0]["id"] == "gh:repo:ledger"
    assert blob(job_id, "analysis_input") is None
    assert blob(job_id, "sources") is None


def test_an_uploaded_cv_is_parsed_in_the_sandbox_and_its_blob_consumed(
    monkeypatch: pytest.MonkeyPatch, fetcher: Fetcher
) -> None:
    use_models(monkeypatch, evidence=[CV_REPLY], assess=[ASSESS_REPLY], recommend=[ADVICE_REPLY])
    job_id = submit(cv_file=make_pdf([text_page()]))

    run(job_id)

    record = load(job_id)
    assert record.status is JobStatus.DONE, record.error_code
    assert record.result is not None
    assert record.result["report"]["coverage"]["cv"] == "read"
    assert blob(job_id, "cv_file") is None


def test_a_failed_cv_next_to_github_evidence_pauses_then_continues(
    monkeypatch: pytest.MonkeyPatch, fetcher: Fetcher
) -> None:
    models = use_models(monkeypatch, assess=[ASSESS_REPLY], recommend=[ADVICE_REPLY])
    job_id = submit(cv_text="far too short to be a CV")

    run(job_id)

    paused = load(job_id)
    assert (paused.status, paused.failed_source, paused.error_code) == (
        JobStatus.NEEDS_DECISION,
        "cv",
        "unreadable_document",
    )
    assert blob(job_id, "cv_text") is None
    assert blob(job_id, "sources") is not None

    resume(job_id, "continue")
    run(job_id)

    done = load(job_id)
    assert done.status is JobStatus.DONE, done.error_code
    assert done.result is not None
    assert done.result["report"]["coverage"]["cv"] == "skipped"
    assert fetcher.calls == 1
    assert models.generators.evidence.calls == []  # type: ignore[attr-defined]


def test_a_rate_limited_github_pauses_with_its_reset_time_and_a_retry_reads_it_again(
    monkeypatch: pytest.MonkeyPatch, fetcher: Fetcher
) -> None:
    models = use_models(
        monkeypatch, evidence=[CV_REPLY], assess=[ASSESS_REPLY], recommend=[ADVICE_REPLY]
    )
    fetcher.error = GitHubError(GitHubFailure.GITHUB_RATE_LIMITED, reset_at=1790000000)
    job_id = submit(cv_text=CV_TEXT)

    run(job_id)

    paused = load(job_id)
    assert (paused.status, paused.failed_source, paused.reset_at) == (
        JobStatus.NEEDS_DECISION,
        "github",
        1790000000,
    )

    fetcher.error = None
    resume(job_id, "retry")
    run(job_id)

    done = load(job_id)
    assert done.status is JobStatus.DONE, done.error_code
    assert fetcher.calls == 2
    assert len(models.generators.evidence.calls) == 1  # type: ignore[attr-defined]


def test_a_failed_only_source_fails_the_analysis_and_deletes_its_inputs(
    monkeypatch: pytest.MonkeyPatch, fetcher: Fetcher
) -> None:
    use_models(monkeypatch)
    job_id = submit(github=False, cv_text="far too short to be a CV")

    run(job_id)

    record = load(job_id)
    assert (record.status, record.error_code) == (JobStatus.FAILED, "unreadable_document")
    assert blob(job_id, "analysis_input") is None


def test_an_analysis_without_its_input_fails_as_input_expired(
    monkeypatch: pytest.MonkeyPatch, fetcher: Fetcher
) -> None:
    use_models(monkeypatch)
    job_id = in_store(lambda store: store.create("match_analysis", "owner", now=time.time())).id

    run(job_id)

    assert load(job_id).error_code == "input_expired"


def test_two_invalid_assessments_fail_as_invalid_output(
    monkeypatch: pytest.MonkeyPatch, fetcher: Fetcher
) -> None:
    use_models(monkeypatch, assess=["{}", "{}"])
    job_id = submit()

    run(job_id)

    assert load(job_id).error_code == "analysis_ai_invalid_output"


def test_a_redelivered_task_for_a_paused_analysis_changes_nothing(
    monkeypatch: pytest.MonkeyPatch, fetcher: Fetcher
) -> None:
    use_models(monkeypatch)
    job_id = submit(cv_text="far too short to be a CV")
    run(job_id)
    before = load(job_id)

    run(job_id)

    assert load(job_id) == before
    assert blob(job_id, "sources") is not None


def test_cv_text_never_reaches_the_log(
    monkeypatch: pytest.MonkeyPatch, fetcher: Fetcher, caplog: pytest.LogCaptureFixture
) -> None:
    use_models(monkeypatch, evidence=[CV_REPLY], assess=[ASSESS_REPLY], recommend=[ADVICE_REPLY])
    job_id = submit(cv_text=CV_TEXT)

    with caplog.at_level("DEBUG"):
        run(job_id)

    assert load(job_id).status is JobStatus.DONE
    assert "analysis finished" in caplog.text
    assert "PostgreSQL schemas" not in caplog.text
    assert "Backend engineer at Acme" not in caplog.text


def test_the_analysis_task_has_its_own_time_limits() -> None:
    task = celery_app.tasks["jobs.run_analysis"]

    assert task.soft_time_limit == settings.match_analysis_soft_time_limit_seconds
    assert task.time_limit == settings.match_analysis_hard_time_limit_seconds
    assert task.time_limit > celery_app.conf.task_time_limit


def test_a_github_retry_with_a_corrected_url_reads_the_new_profile(
    monkeypatch: pytest.MonkeyPatch, fetcher: Fetcher
) -> None:
    use_models(monkeypatch, evidence=[CV_REPLY], assess=[ASSESS_REPLY], recommend=[ADVICE_REPLY])
    fetcher.error = GitHubError(GitHubFailure.GITHUB_USER_NOT_FOUND)
    job_id = submit(cv_text=CV_TEXT)
    run(job_id)
    assert load(job_id).failed_source == "github"

    fetcher.error = None
    corrected = f"https://github.com/fixed{uuid.uuid4().hex[:8]}"
    in_store(
        lambda store: store.resume(
            job_id,
            "owner",
            resume="retry",
            now=time.time(),
            blob=("github_url", corrected.encode(), 60),
        )
    )
    run(job_id)

    assert load(job_id).status is JobStatus.DONE
    assert fetcher.usernames[-1] == corrected.rsplit("/", 1)[1]


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("ai_invalid_output", "analysis_ai_invalid_output"),
        ("input_too_long", "analysis_input_too_long"),
        ("ai_unavailable", "ai_unavailable"),
    ],
)
def test_assessment_failures_get_analysis_specific_codes(code: str, expected: str) -> None:
    assert tasks.analysis_failure_code(code) == expected

