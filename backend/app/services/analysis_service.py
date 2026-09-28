import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from app.ai.embeddings import Embedder
from app.ai.generation import Generator
from app.ai.input_guard import detect_injection_phrases
from app.ai.match.assess import Assessment, assess
from app.ai.match.dedup import merge_evidence
from app.ai.match.preselect import preselect
from app.ai.match.recommend import Recommendations, recommend
from app.ai.match.requirements import RequirementRef, requirement_refs
from app.ai.match.schemas import EvidenceItem, JobPosting
from app.ai.match.structured import ExtractionError
from app.match.scoring import ScoredRequirement, refusal_reasons, score
from app.schemas.match import MatchReport
from app.services.analysis_sources import SourcesState, StageCallback
from app.services.match_report import build_report, refusal_report

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class AnalysisMetrics:
    requirements: int
    evidence_items: int
    refused: bool
    cited: int = 0
    dropped_citations: int = 0
    downgraded: int = 0
    dropped_advice: int = 0
    advice_error: str | None = None


@dataclass(frozen=True, slots=True)
class AnalysisOutcome:
    report: MatchReport
    metrics: AnalysisMetrics


def scored_requirements(
    requirements: Sequence[RequirementRef],
    assessment: Assessment | None,
    evidence: Mapping[str, EvidenceItem],
) -> list[ScoredRequirement]:
    results = {r.requirement.id: r for r in assessment.results} if assessment else {}
    scored = []
    for requirement in requirements:
        result = results.get(requirement.id)
        if requirement.sensitive:
            scored.append(ScoredRequirement(requirement.importance, "not_assessed"))
        elif result is None:
            scored.append(ScoredRequirement(requirement.importance, "not_demonstrated"))
        else:
            kinds = frozenset(evidence[i].kind for i in result.evidence_ids if i in evidence)
            scored.append(ScoredRequirement(requirement.importance, result.status, kinds))
    return scored


async def _advice(
    generator: Generator, title: str, assessment: Assessment, evidence: Mapping[str, EvidenceItem]
) -> tuple[Recommendations | None, str | None]:
    try:
        return await recommend(generator, title, assessment, evidence), None
    except ExtractionError as exc:
        # The score stands on its own; losing the advice must not lose the analysis.
        return None, exc.code


async def analyse(
    posting: JobPosting,
    sources: SourcesState,
    *,
    embedder: Embedder,
    assess_generator: Generator,
    recommend_generator: Generator,
    on_stage: StageCallback,
    top_k: int,
    min_similarity: float,
) -> AnalysisOutcome:
    requirements = requirement_refs(posting)
    assessable = [r for r in requirements if not r.sensitive]
    evidence = merge_evidence(sources.cv.items, sources.github.items)
    by_id = {item.id: item for item in evidence}
    flagged = detect_injection_phrases("\n".join(r.text for r in requirements))
    if flagged:
        logger.warning("analysis injection phrasing in requirements patterns=%s", ",".join(flagged))

    await on_stage("matching")
    selection = preselect(assessable, evidence, embedder, top_k=top_k)
    refusal = refusal_reasons(
        scored_requirements(requirements, None, by_id),
        evidence_items=len(evidence),
        best_similarity=selection.best_similarity,
        min_similarity=min_similarity,
    )
    if refusal:
        await on_stage("scoring")
        return AnalysisOutcome(
            report=refusal_report(refusal, sources=sources, model=assess_generator.model_name),
            metrics=AnalysisMetrics(len(requirements), len(evidence), refused=True),
        )

    await on_stage("assessing")
    assessment = await assess(assess_generator, assessable, by_id, selection)
    await on_stage("scoring")
    total = score(scored_requirements(requirements, assessment, by_id))
    await on_stage("recommending")
    advice, advice_error = await _advice(recommend_generator, posting.title, assessment, by_id)
    report = build_report(
        requirements=requirements,
        assessment=assessment,
        score=total,
        advice=advice,
        evidence=by_id,
        sources=sources,
        model=assess_generator.model_name,
    )
    return AnalysisOutcome(
        report=report,
        metrics=AnalysisMetrics(
            requirements=len(requirements),
            evidence_items=len(evidence),
            refused=False,
            cited=assessment.cited,
            dropped_citations=assessment.dropped,
            downgraded=assessment.downgraded,
            dropped_advice=advice.dropped if advice else 0,
            advice_error=advice_error,
        ),
    )
