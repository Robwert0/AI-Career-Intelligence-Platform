"""The public sample report must be exactly what the real pipeline would emit for its inputs.

Only the model's outputs (statuses, rationales, cited ids, advice text) are hand-written. Every
derived field -- score, breakdown, coverage, summary, hard gaps, limitations -- is recomputed
here by production code and compared against the fixture byte for byte.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from app.ai.match.assess import AssessedRequirement, Assessment
from app.ai.match.recommend import (
    Recommendation,
    Recommendations,
    Rewrite,
    allowed_ids,
    invents_facts,
    rewritable_evidence,
)
from app.ai.match.requirements import RequirementRef
from app.ai.match.schemas import EvidenceItem
from app.match.scoring import ScoredRequirement, score
from app.schemas.match import MatchReport
from app.services.analysis_sources import CvSource, GitHubSource, SourcesState
from app.services.match_report import SENSITIVE_RATIONALE, build_report

SAMPLE = Path(__file__).parents[2] / "frontend/lib/sample/match-report.sample.json"


@pytest.fixture(scope="module")
def sample() -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(SAMPLE.read_text())
    return loaded


def _evidence(sample: dict[str, Any]) -> dict[str, EvidenceItem]:
    items: dict[str, EvidenceItem] = {}
    for requirement in sample["requirements"]:
        for out in requirement["evidence"]:
            item = EvidenceItem(
                id=out["id"],
                sources=(out["source"],),
                kind=out["kind"],
                section_label=out["section_label"],
                text=out["text"],
                url=out["url"],
            )
            assert items.setdefault(item.id, item) == item, f"{item.id} differs between citations"
    return items


def _inputs(
    sample: dict[str, Any],
) -> tuple[list[RequirementRef], Assessment, dict[str, EvidenceItem]]:
    refs: list[RequirementRef] = []
    results: list[AssessedRequirement] = []
    for row in sample["requirements"]:
        ref = RequirementRef(
            id=row["id"],
            text=row["text"],
            importance=row["importance"],
            sensitive=row["status"] == "not_assessed",
        )
        refs.append(ref)
        if row["status"] != "not_assessed":
            results.append(
                AssessedRequirement(
                    requirement=ref,
                    status=row["status"],
                    evidence_ids=tuple(item["id"] for item in row["evidence"]),
                    rationale=row["rationale"],
                )
            )
    assessment = Assessment(results=tuple(results), cited=0, dropped=0, downgraded=0, calls=1)
    return refs, assessment, _evidence(sample)


def _advice(sample: dict[str, Any]) -> Recommendations:
    def recs(key: str) -> tuple[Recommendation, ...]:
        return tuple(
            Recommendation(r["requirement_id"], r["title"], r["detail"])
            for r in sample["recommendations"][key]
        )

    return Recommendations(
        immediate=recs("immediate"),
        longer_term=recs("longer_term"),
        rewrites=tuple(
            Rewrite(r["evidence_id"], r["before"], r["after"], tuple(r["questions"]))
            for r in sample["rewrites"]
        ),
        dropped=0,
    )


def _sources(sample: dict[str, Any], evidence: dict[str, EvidenceItem]) -> SourcesState:
    github = sample["coverage"]["github"]
    return SourcesState(
        cv=CvSource(
            status=sample["coverage"]["cv"],
            items=tuple(item for item in evidence.values() if "cv" in item.sources),
        ),
        github=GitHubSource(
            status=github["status"],
            items=tuple(item for item in evidence.values() if "github" in item.sources),
            inspected_repos=github["inspected_repos"],
            public_non_fork_repos=github["public_non_fork_repos"],
            readmes_found=github["readmes_found"],
        ),
    )


def _score(sample: dict[str, Any]) -> int:
    return score(
        [
            ScoredRequirement(
                importance=row["importance"],
                status=row["status"],
                evidence_kinds=frozenset(item["kind"] for item in row["evidence"]),
            )
            for row in sample["requirements"]
        ]
    ).total


def test_sample_matches_the_contract(sample: dict[str, Any]) -> None:
    MatchReport.model_validate(sample)


def test_sample_is_what_build_report_emits_for_its_inputs(sample: dict[str, Any]) -> None:
    refs, assessment, evidence = _inputs(sample)
    scored = score(
        [
            ScoredRequirement(
                importance=ref.importance,
                status=row["status"],
                evidence_kinds=frozenset(item["kind"] for item in row["evidence"]),
            )
            for ref, row in zip(refs, sample["requirements"], strict=True)
        ]
    )

    report = build_report(
        requirements=refs,
        assessment=assessment,
        score=scored,
        advice=_advice(sample),
        evidence=evidence,
        sources=_sources(sample, evidence),
        model=sample["model"],
    )

    assert report.model_dump(mode="json") == sample


def test_changing_one_status_changes_the_score(sample: dict[str, Any]) -> None:
    # Guards the test above against comparing the fixture with itself.
    downgraded = json.loads(json.dumps(sample))
    downgraded["requirements"][0]["status"] = "partial"

    assert _score(downgraded) < _score(sample) == sample["score"]


def test_sample_covers_every_report_feature(sample: dict[str, Any]) -> None:
    statuses = {row["status"] for row in sample["requirements"]}
    kinds = {item["kind"] for row in sample["requirements"] for item in row["evidence"]}

    assert {"demonstrated", "partial", "not_demonstrated", "not_assessed"} <= statuses
    assert {"work", "project", "repo", "skill_list"} <= kinds
    assert sample["summary"]["gaps"]
    assert sample["recommendations"]["immediate"]
    assert sample["recommendations"]["longer_term"]
    assert sample["rewrites"]


def test_sample_advice_obeys_the_recommend_guards(sample: dict[str, Any]) -> None:
    _, assessment, evidence = _inputs(sample)
    allowed = set(allowed_ids(assessment))
    rewritable = {item.id: item for item in rewritable_evidence(assessment, evidence)}
    advice = sample["recommendations"]["immediate"] + sample["recommendations"]["longer_term"]

    assert {item["requirement_id"] for item in advice} <= allowed
    for rewrite in sample["rewrites"]:
        source = rewritable[rewrite["evidence_id"]]
        assert rewrite["before"] == source.text
        assert not invents_facts(source.text, rewrite["after"]), rewrite["after"]
        assert rewrite["questions"]


def test_not_assessed_rows_use_the_pipeline_wording(sample: dict[str, Any]) -> None:
    rows = [row for row in sample["requirements"] if row["status"] == "not_assessed"]

    assert rows
    assert all(row["rationale"] == SENSITIVE_RATIONALE for row in rows)


def test_sample_links_to_no_real_account(sample: dict[str, Any]) -> None:
    urls = [item["url"] for row in sample["requirements"] for item in row["evidence"]]

    assert urls and all(url is None for url in urls)
