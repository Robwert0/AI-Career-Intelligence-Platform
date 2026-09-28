from collections.abc import Mapping, Sequence

from app.ai.match.assess import AssessedRequirement, Assessment
from app.ai.match.recommend import Recommendations as Advice
from app.ai.match.requirements import RequirementRef
from app.ai.match.schemas import EvidenceItem
from app.match.scoring import WEIGHTS, RefusalCode, Score, coverage_level
from app.schemas.match import (
    BreakdownRowOut,
    Coverage,
    EvidenceOut,
    GitHubCoverage,
    MatchReport,
    RecommendationOut,
    Recommendations,
    Refusal,
    RequirementOut,
    RewriteOut,
    SourceStatus,
    Summary,
)
from app.services.analysis_sources import CvSource, GitHubSource, SourcesState

DISCLAIMER = (
    "This is an alignment estimate from the evidence you supplied. It is not a hiring "
    "probability or an employer's ATS score."
)
SENSITIVE_RATIONALE = (
    "This concerns a personal characteristic or work authorisation, so it was not assessed. "
    "Confirm it yourself."
)
GITHUB_PUBLIC_ONLY = "GitHub shows public repositories only; professional work is often private"
GITHUB_METADATA_ONLY = "GitHub was inspected via metadata and READMEs; no code was reviewed"
CV_TRUNCATED = "Your CV was longer than we read; only its first part was analysed"
CV_UNVERIFIED = (
    "Some statements in your CV could not be verified against its text and were left out"
)
# Share of extracted CV items dropped by grounding above which the report says so.
CV_DROPPED_SHARE = 0.25
CV_SKIPPED = "Your CV could not be read, so this report uses your GitHub profile only"
GITHUB_SKIPPED = "Your GitHub profile could not be read, so this report uses your CV only"
NO_PREFERRED = (
    "The posting lists no preferred requirements, so their weight was shared across the other "
    "categories"
)
SENSITIVE_SKIPPED = (
    "Requirements about personal characteristics or work authorisation were not assessed"
)
ADVICE_MISSING = "Recommendations could not be generated this time; the score is unaffected"

REFUSALS: dict[RefusalCode, tuple[str, str]] = {
    "insufficient_job": (
        "The posting has fewer than 3 requirements we can assess, or no required ones.",
        "Add the posting's qualifications in the preview: at least 3, with at least one required.",
    ),
    "insufficient_evidence": (
        "We found fewer than 3 pieces of evidence in what you supplied.",
        "Upload a fuller CV, or add your GitHub profile.",
    ),
    "unrelated_sources": (
        "None of your evidence relates to this posting's requirements.",
        "Check that you supplied the right CV for this job.",
    ),
}


def _status(source: CvSource | GitHubSource) -> SourceStatus:
    # "pending" never survives read_sources; treat it as not read rather than crash a report.
    return "failed" if source.status == "pending" else source.status


def _coverage(
    sources: SourcesState, *, with_evidence: float, extra: Sequence[str] = ()
) -> Coverage:
    provided = [s for s in (sources.cv, sources.github) if s.status != "not_provided"]
    limitations: list[str] = []
    if sources.github.status == "read":
        limitations += [GITHUB_PUBLIC_ONLY, GITHUB_METADATA_ONLY]
    if sources.cv.status == "read" and sources.cv.truncated:
        limitations.append(CV_TRUNCATED)
    extracted = sources.cv.dropped + len(sources.cv.items)
    if sources.cv.dropped and sources.cv.dropped / extracted >= CV_DROPPED_SHARE:
        limitations.append(CV_UNVERIFIED)
    if sources.cv.status == "skipped":
        limitations.append(CV_SKIPPED)
    if sources.github.status == "skipped":
        limitations.append(GITHUB_SKIPPED)
    limitations += extra
    return Coverage(
        level=coverage_level(
            with_evidence, every_source_read=all(s.status == "read" for s in provided)
        ),
        cv=_status(sources.cv),
        github=GitHubCoverage(
            status=_status(sources.github),
            inspected_repos=sources.github.inspected_repos,
            public_non_fork_repos=sources.github.public_non_fork_repos,
            readmes_found=sources.github.readmes_found,
        ),
        requirements_with_evidence=round(with_evidence, 3),
        limitations=limitations,
    )


def _evidence_out(item: EvidenceItem) -> EvidenceOut:
    return EvidenceOut(
        id=item.id,
        source="cv" if "cv" in item.sources else "github",
        kind=item.kind,
        section_label=item.section_label,
        text=item.text,
        url=item.url,
    )


def _requirement_out(
    requirement: RequirementRef,
    result: AssessedRequirement | None,
    evidence: Mapping[str, EvidenceItem],
) -> RequirementOut:
    if result is None:
        return RequirementOut(
            id=requirement.id,
            text=requirement.text,
            importance=requirement.importance,
            status="not_assessed",
            rationale=SENSITIVE_RATIONALE,
            hard_gap=False,
            evidence=[],
        )
    return RequirementOut(
        id=requirement.id,
        text=requirement.text,
        importance=requirement.importance,
        status=result.status,
        rationale=result.rationale,
        hard_gap=requirement.importance == "required" and result.status == "unmet",
        evidence=[_evidence_out(evidence[i]) for i in result.evidence_ids if i in evidence],
    )


def _summary(rows: Sequence[RequirementOut]) -> Summary:
    strongest = [row.text for row in rows if row.status == "demonstrated"]
    gaps = [row.text for row in rows if row.hard_gap] + [
        row.text
        for row in rows
        if row.importance == "required" and row.status == "not_demonstrated"
    ]
    return Summary(strongest=strongest[:3], gaps=gaps[:3])


def build_report(
    *,
    requirements: Sequence[RequirementRef],
    assessment: Assessment,
    score: Score,
    advice: Advice | None,
    evidence: Mapping[str, EvidenceItem],
    sources: SourcesState,
    model: str,
) -> MatchReport:
    by_id = {result.requirement.id: result for result in assessment.results}
    rows = [_requirement_out(r, by_id.get(r.id), evidence) for r in requirements]
    assessed = [row for row in rows if row.status != "not_assessed"]
    with_evidence = sum(bool(row.evidence) for row in assessed) / len(assessed) if assessed else 0.0
    extra: list[str] = []
    if "preferred" in score.redistributed:
        extra.append(NO_PREFERRED)
    if len(assessed) < len(rows):
        extra.append(SENSITIVE_SKIPPED)
    if advice is None:
        extra.append(ADVICE_MISSING)
    return MatchReport(
        score=score.total,
        refusal=None,
        summary=_summary(rows),
        breakdown=[
            BreakdownRowOut(
                category=row.category,
                weight=row.weight,
                effective_weight=row.effective_weight,
                score=row.score,
                points=row.points,
            )
            for row in score.breakdown
        ],
        coverage=_coverage(sources, with_evidence=with_evidence, extra=extra),
        requirements=rows,
        recommendations=Recommendations(
            immediate=[
                RecommendationOut(requirement_id=r.requirement_id, title=r.title, detail=r.detail)
                for r in (advice.immediate if advice else ())
            ],
            longer_term=[
                RecommendationOut(requirement_id=r.requirement_id, title=r.title, detail=r.detail)
                for r in (advice.longer_term if advice else ())
            ],
        ),
        rewrites=[
            RewriteOut(
                evidence_id=r.evidence_id,
                before=r.before,
                after=r.after,
                questions=list(r.questions),
            )
            for r in (advice.rewrites if advice else ())
        ],
        disclaimer=DISCLAIMER,
        model=model,
    )


def refusal_report(
    codes: Sequence[RefusalCode], *, sources: SourcesState, model: str
) -> MatchReport:
    return MatchReport(
        score=None,
        refusal=Refusal(
            reasons=[REFUSALS[code][0] for code in codes],
            needed=[REFUSALS[code][1] for code in codes],
        ),
        summary=Summary(),
        breakdown=[
            BreakdownRowOut(
                category=category, weight=weight, effective_weight=0.0, score=0.0, points=0.0
            )
            for category, weight in WEIGHTS.items()
        ],
        coverage=_coverage(sources, with_evidence=0.0),
        requirements=[],
        recommendations=Recommendations(),
        rewrites=[],
        disclaimer=DISCLAIMER,
        model=model,
    )
