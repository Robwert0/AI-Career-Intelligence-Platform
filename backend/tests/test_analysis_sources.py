import pytest

from app.ai.match.evidence_extract import CvEvidence
from app.ai.match.schemas import EvidenceItem, JobPosting
from app.schemas.match import AnalysisInput
from app.services.analysis_sources import (
    CvSource,
    Fail,
    GitHubSource,
    Pause,
    Ready,
    SourcesState,
    apply_decision,
    decide,
    initial_sources,
    read_sources,
)
from app.services.candidate_evidence import CvReading, GitHubReading, SourceError

POSTING = JobPosting(title="Backend Engineer")
GH_URL = "https://github.com/jane"
CV_ITEM = EvidenceItem(
    id="cv:experience:0",
    sources=("cv",),
    kind="work",
    section_label="Experience · Acme",
    text="Built Go services.",
)
REPO_ITEM = EvidenceItem(
    id="gh:repo:ledger",
    sources=("github",),
    kind="repo",
    section_label="GitHub · ledger",
    text="Ledger in Go.",
    url="https://github.com/jane/ledger",
)


class Blobs:
    def __init__(self, **blobs: bytes) -> None:
        self.blobs = dict(blobs)
        self.taken: list[str] = []

    async def __call__(self, name: str) -> bytes | None:
        self.taken.append(name)
        return self.blobs.pop(name, None)


class CvReader:
    def __init__(self, error: str | None = None) -> None:
        self.error = error
        self.calls: list[tuple[bytes | None, str | None]] = []

    async def __call__(self, *, file: bytes | None = None, text: str | None = None) -> CvReading:
        self.calls.append((file, text))
        if self.error:
            raise SourceError(self.error)
        return CvReading(
            evidence=CvEvidence(items=(CV_ITEM,), input_truncated=False, dropped=0),
            document_kind="pdf" if file else "text",
            pages=1 if file else None,
            truncated=True,
        )


class GitHubReader:
    def __init__(
        self, error: SourceError | None = None, items: tuple[EvidenceItem, ...] = (REPO_ITEM,)
    ) -> None:
        self.error = error
        self.items = items
        self.calls: list[str] = []

    async def __call__(self, url: str) -> GitHubReading:
        self.calls.append(url)
        if self.error:
            raise self.error
        return GitHubReading(
            items=self.items,
            username="jane",
            public_repos=23,
            candidate_repos=17,
            inspected_repos=10,
            readmes_found=8,
        )


class Stages:
    def __init__(self) -> None:
        self.seen: list[str] = []

    async def __call__(self, stage: str) -> None:
        self.seen.append(stage)


def both() -> SourcesState:
    return initial_sources(AnalysisInput(posting=POSTING, github_url=GH_URL, cv_provided=True))


async def test_both_sources_are_read_in_order() -> None:
    blobs, stages, cv, gh = Blobs(cv_file=b"%PDF-1.4"), Stages(), CvReader(), GitHubReader()

    state = await read_sources(both(), take_cv=blobs, read_cv=cv, read_github=gh, on_stage=stages)

    assert stages.seen == ["reading_cv", "reading_github"]
    assert cv.calls == [(b"%PDF-1.4", None)]
    assert gh.calls == [GH_URL]
    assert state.cv == CvSource(status="read", items=(CV_ITEM,), truncated=True)
    assert (
        state.github.status,
        state.github.inspected_repos,
        state.github.public_non_fork_repos,
    ) == ("read", 10, 17)
    assert decide(state) == Ready()


async def test_the_cv_blob_is_taken_before_it_is_parsed() -> None:
    blobs = Blobs(cv_file=b"%PDF-1.4")

    async def check_gone(*, file: bytes | None = None, text: str | None = None) -> CvReading:
        assert "cv_file" not in blobs.blobs
        return await CvReader()(file=file, text=text)

    await read_sources(
        both(), take_cv=blobs, read_cv=check_gone, read_github=GitHubReader(), on_stage=Stages()
    )


async def test_pasted_cv_text_is_decoded_and_read() -> None:
    cv = CvReader()

    await read_sources(
        both(),
        take_cv=Blobs(cv_text="Café engineer".encode()),
        read_cv=cv,
        read_github=GitHubReader(),
        on_stage=Stages(),
    )

    assert cv.calls == [(None, "Café engineer")]


async def test_a_missing_cv_blob_fails_the_cv_as_input_expired() -> None:
    state = await read_sources(
        both(), take_cv=Blobs(), read_cv=CvReader(), read_github=GitHubReader(), on_stage=Stages()
    )

    assert (state.cv.status, state.cv.error_code) == ("failed", "input_expired")


async def test_sources_not_provided_are_never_read() -> None:
    only_github = initial_sources(AnalysisInput(posting=POSTING, github_url=GH_URL))
    cv, stages = CvReader(), Stages()

    state = await read_sources(
        only_github, take_cv=Blobs(), read_cv=cv, read_github=GitHubReader(), on_stage=stages
    )

    assert cv.calls == []
    assert stages.seen == ["reading_github"]
    assert state.cv.status == "not_provided"


async def test_a_failed_source_next_to_a_useful_one_pauses_for_a_decision() -> None:
    state = await read_sources(
        both(),
        take_cv=Blobs(cv_file=b"x"),
        read_cv=CvReader("scanned_pdf_suspected"),
        read_github=GitHubReader(),
        on_stage=Stages(),
    )

    assert decide(state) == Pause(source="cv", code="scanned_pdf_suspected", reset_at=None)


async def test_a_github_pause_carries_the_reset_time() -> None:
    state = await read_sources(
        both(),
        take_cv=Blobs(cv_file=b"x"),
        read_cv=CvReader(),
        read_github=GitHubReader(SourceError("github_rate_limited", reset_at=1790000000)),
        on_stage=Stages(),
    )

    assert decide(state) == Pause(source="github", code="github_rate_limited", reset_at=1790000000)


async def test_a_failed_only_source_fails_the_analysis() -> None:
    only_cv = initial_sources(AnalysisInput(posting=POSTING, cv_provided=True))

    state = await read_sources(
        only_cv,
        take_cv=Blobs(cv_text=b"x"),
        read_cv=CvReader("not_a_cv"),
        read_github=GitHubReader(),
        on_stage=Stages(),
    )

    assert decide(state) == Fail(code="not_a_cv")


async def test_a_failure_next_to_a_source_with_no_evidence_fails_too() -> None:
    state = await read_sources(
        both(),
        take_cv=Blobs(cv_file=b"x"),
        read_cv=CvReader("unreadable_document"),
        read_github=GitHubReader(items=()),
        on_stage=Stages(),
    )

    assert decide(state) == Fail(code="unreadable_document")


async def test_both_failing_reports_the_cv_failure() -> None:
    state = await read_sources(
        both(),
        take_cv=Blobs(cv_file=b"x"),
        read_cv=CvReader("encrypted_pdf"),
        read_github=GitHubReader(SourceError("github_unavailable")),
        on_stage=Stages(),
    )

    assert decide(state) == Fail(code="encrypted_pdf")


def paused_on_cv() -> SourcesState:
    return SourcesState(
        cv=CvSource(status="failed", error_code="scanned_pdf_suspected"),
        github=GitHubSource(status="read", url=GH_URL, items=(REPO_ITEM,)),
    )


async def test_continue_skips_the_failed_source_and_keeps_the_other() -> None:
    state = apply_decision(paused_on_cv(), source="cv", resume="continue")
    gh = GitHubReader()

    after = await read_sources(
        state, take_cv=Blobs(), read_cv=CvReader(), read_github=gh, on_stage=Stages()
    )

    assert after.cv.status == "skipped"
    assert after.github.items == (REPO_ITEM,)
    assert gh.calls == []
    assert decide(after) == Ready()


async def test_retry_reads_only_the_failed_source_again() -> None:
    state = apply_decision(paused_on_cv(), source="cv", resume="retry")
    cv, gh = CvReader(), GitHubReader()

    after = await read_sources(
        state, take_cv=Blobs(cv_text=b"new text"), read_cv=cv, read_github=gh, on_stage=Stages()
    )

    assert cv.calls == [(None, "new text")]
    assert gh.calls == []
    assert after.cv.status == "read"


@pytest.mark.parametrize(
    ("source", "resume"), [("github", "continue"), ("cv", "restart"), ("x", "retry")]
)
def test_a_directive_that_does_not_match_the_state_changes_nothing(
    source: str, resume: str
) -> None:
    assert apply_decision(paused_on_cv(), source=source, resume=resume) == paused_on_cv()


def test_the_state_round_trips_through_its_json_checkpoint() -> None:
    state = paused_on_cv()

    assert SourcesState.model_validate_json(state.model_dump_json()) == state
