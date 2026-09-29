import functools
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Self

from pydantic import model_validator

from app.ai.generation import Generator, SamplingSettings
from app.ai.match.preselect import Preselection
from app.ai.match.prompts import build_assess_messages
from app.ai.match.requirements import RequirementRef
from app.ai.match.schemas import AssessedItem, AssessReply, AssessStatus, EvidenceItem
from app.ai.match.structured import generate_validated

ASSESS_BATCH_SIZE = 4
MAX_ASSESS_BATCHES = 8
ASSESS_SAMPLING = SamplingSettings(temperature=0.0, seed=0, max_output_tokens=2048)
UNVERIFIED_RATIONALE = "No cited evidence could be verified for this requirement."
NO_EVIDENCE_RATIONALE = "No evidence addressing this requirement was found."


@dataclass(frozen=True, slots=True)
class AssessedRequirement:
    requirement: RequirementRef
    status: AssessStatus
    evidence_ids: tuple[str, ...]
    rationale: str


@dataclass(frozen=True, slots=True)
class Assessment:
    results: tuple[AssessedRequirement, ...]
    cited: int
    dropped: int
    downgraded: int
    calls: int


def batches(
    requirements: Sequence[RequirementRef],
    *,
    size: int = ASSESS_BATCH_SIZE,
    max_batches: int = MAX_ASSESS_BATCHES,
) -> list[list[RequirementRef]]:
    # Batches grow past `size` only for very long postings, so the call count stays bounded.
    size = max(size, math.ceil(len(requirements) / max_batches))
    return [list(requirements[start : start + size]) for start in range(0, len(requirements), size)]


@functools.cache
def reply_model(size: int) -> type[AssessReply]:
    expected = sorted(f"R{number}" for number in range(1, size + 1))

    class SizedAssessReply(AssessReply):
        @model_validator(mode="after")
        def _every_requirement_exactly_once(self) -> Self:
            if sorted(item.ref for item in self.assessments) != expected:
                raise ValueError("assess every requirement exactly once")
            return self

    return SizedAssessReply


@dataclass(frozen=True, slots=True)
class _Checked:
    result: AssessedRequirement
    cited: int
    dropped: int
    downgraded: bool


def _check(item: AssessedItem, requirement: RequirementRef, allowed: Sequence[str]) -> _Checked:
    cited = tuple(dict.fromkeys(item.evidence_ids))
    kept = tuple(evidence_id for evidence_id in cited if evidence_id in allowed)
    status: AssessStatus = item.status
    rationale = item.rationale.strip()
    downgraded = False
    if status == "not_demonstrated":
        kept = ()
    elif not kept:
        # A claim that no verifiable evidence backs is not a claim the report may make.
        status, rationale, downgraded = "not_demonstrated", UNVERIFIED_RATIONALE, True
    return _Checked(
        result=AssessedRequirement(
            requirement=requirement,
            status=status,
            evidence_ids=kept,
            rationale=rationale or NO_EVIDENCE_RATIONALE,
        ),
        cited=len(cited),
        dropped=len(cited) - sum(evidence_id in allowed for evidence_id in cited),
        downgraded=downgraded,
    )


async def assess(
    generator: Generator,
    requirements: Sequence[RequirementRef],
    evidence: Mapping[str, EvidenceItem],
    preselection: Preselection,
) -> Assessment:
    results: list[AssessedRequirement] = []
    cited = dropped = downgraded = calls = 0
    for batch in batches(requirements):
        refs = {f"R{number}": requirement for number, requirement in enumerate(batch, start=1)}
        shown = list(
            dict.fromkeys(
                evidence_id
                for requirement in batch
                for evidence_id in preselection.ids_for(requirement.id)
            )
        )
        messages = build_assess_messages(
            [
                (ref, requirement.text, preselection.ids_for(requirement.id))
                for ref, requirement in refs.items()
            ],
            [evidence[evidence_id] for evidence_id in shown],
        )
        reply = await generate_validated(
            generator, messages, reply_model(len(batch)), ASSESS_SAMPLING
        )
        calls += 1
        by_ref = {item.ref: item for item in reply.assessments}
        for ref, requirement in refs.items():
            checked = _check(by_ref[ref], requirement, preselection.ids_for(requirement.id))
            results.append(checked.result)
            cited += checked.cited
            dropped += checked.dropped
            downgraded += checked.downgraded
    return Assessment(
        results=tuple(results), cited=cited, dropped=dropped, downgraded=downgraded, calls=calls
    )
