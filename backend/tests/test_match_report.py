from app.ai.match.assess import AssessedRequirement, Assessment
from app.ai.match.requirements import RequirementRef
from app.ai.match.schemas import EvidenceItem
from app.match.scoring import ScoredRequirement, score
from app.schemas.match import MatchReport
from app.services.analysis_sources import CvSource, GitHubSource, SourcesState
from app.services.match_report import (
    CV_SKIPPED,
    CV_TRUNCATED,
    DISCLAIMER,
    GITHUB_METADATA_ONLY,
    GITHUB_PUBLIC_ONLY,
    NO_PREFERRED,
    build_report,
    refusal_report,
)

MERGED = EvidenceItem(
    id="cv:project:0",
    sources=("cv", "github"),
    kind="project",
    section_label="Projects · Jarvis",
    text="Voice assistant in Python.",
    url="https://github.com/jane/jarvis",
)
REPO = EvidenceItem(
    id="gh:repo:ledger",
    sources=("github",),
    kind="repo",
    section_label="GitHub · ledger",
    text="Ledger in Go.",
    url="https://github.com/jane/ledger",
)
EVIDENCE = {MERGED.id: MERGED, REPO.id: REPO}
REQS = [
    RequirementRef(f"req:required:{i}", text, "required", False)
    for i, text in enumerate(["Python", "Go", "Rust"])
]
ASSESSMENT = Assessment(
    results=(
        AssessedRequirement(REQS[0], "demonstrated", (MERGED.id,), "Built one."),
        AssessedRequirement(REQS[1], "demonstrated", (REPO.id,), "Has a repo."),
        AssessedRequirement(REQS[2], "not_demonstrated", (), "Nothing found."),
    ),
    cited=2,
    dropped=0,
    downgraded=0,
    calls=1,
)
BOTH_READ = SourcesState(
    cv=CvSource(status="read", items=(MERGED,), truncated=True),
    github=GitHubSource(
        status="read",
        url="https://github.com/jane",
        items=(REPO,),
        inspected_repos=10,
        public_non_fork_repos=17,
        readmes_found=8,
    ),
)


def report(sources: SourcesState = BOTH_READ) -> MatchReport:
    total = score(
        [
            ScoredRequirement("required", r.status, frozenset({"project"}))
            for r in ASSESSMENT.results
        ]
    )
    return build_report(
        requirements=REQS,
        assessment=ASSESSMENT,
        score=total,
        advice=None,
        evidence=EVIDENCE,
        sources=sources,
        model="ollama/qwen3:8b",
    )


def test_a_merged_item_is_cited_as_cv_evidence_that_links_its_repo() -> None:
    built = report()

    first, second = built.requirements[0].evidence[0], built.requirements[1].evidence[0]
    assert (first.source, first.url) == ("cv", "https://github.com/jane/jarvis")
    assert (second.source, second.kind) == ("github", "repo")


def test_coverage_counts_assessed_requirements_with_cited_evidence() -> None:
    coverage = report().coverage

    assert coverage.requirements_with_evidence == 0.667
    assert coverage.level == "medium"
    assert (
        coverage.github.inspected_repos,
        coverage.github.public_non_fork_repos,
        coverage.github.readmes_found,
    ) == (10, 17, 8)


def test_limitations_explain_scope_truncation_and_redistribution() -> None:
    limitations = report().coverage.limitations

    assert limitations[:2] == [GITHUB_PUBLIC_ONLY, GITHUB_METADATA_ONLY]
    assert CV_TRUNCATED in limitations
    assert NO_PREFERRED in limitations


def test_a_skipped_source_lowers_coverage_and_is_explained() -> None:
    skipped = SourcesState(
        cv=CvSource(status="skipped", error_code="scanned_pdf_suspected"), github=BOTH_READ.github
    )

    coverage = report(skipped).coverage

    assert coverage.cv == "skipped"
    assert CV_SKIPPED in coverage.limitations


def test_the_summary_names_strengths_and_required_gaps() -> None:
    summary = report().summary

    assert (summary.strongest, summary.gaps) == (["Python", "Go"], ["Rust"])


def test_a_refusal_report_has_no_score_and_zero_rows() -> None:
    refused = refusal_report(["insufficient_evidence"], sources=BOTH_READ, model="m")

    assert refused.score is None
    assert (
        refused.refusal is not None
        and len(refused.refusal.reasons) == len(refused.refusal.needed) == 1
    )
    assert [(row.category, row.weight, row.points) for row in refused.breakdown] == [
        ("required", 70, 0.0),
        ("preferred", 20, 0.0),
        ("applied_evidence", 10, 0.0),
    ]
    assert refused.coverage.level == "low"
    assert refused.disclaimer == DISCLAIMER
