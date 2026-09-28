import functools
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from pydantic import Field, JsonValue, create_model

from app.ai.generation import Generator, SamplingSettings
from app.ai.match.assess import Assessment
from app.ai.match.prompts import build_recommend_messages
from app.ai.match.schemas import EvidenceItem, RecommendationItem, RecommendReply, RewriteItem
from app.ai.match.structured import generate_validated

RECOMMEND_SAMPLING = SamplingSettings(temperature=0.0, seed=0, max_output_tokens=2048)
_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")


def _choice(ids: tuple[str, ...]) -> Any:
    # Validation stays a plain id, so a bad one is dropped by code; the enum only steers
    # the model's grammar. A local model given a free string answers "0" for "req:required:0".
    # An empty enum is not a valid grammar; with no ids the list itself is capped at 0.
    extra: dict[str, JsonValue] | None = {"enum": list(ids)} if ids else None
    return (str, Field(max_length=120, json_schema_extra=extra))


@functools.cache
def reply_model(
    requirement_ids: tuple[str, ...], evidence_ids: tuple[str, ...]
) -> type[RecommendReply]:
    advice = create_model(
        "RecommendationChoice", __base__=RecommendationItem, requirement_id=_choice(requirement_ids)
    )
    rewrite = create_model("RewriteChoice", __base__=RewriteItem, evidence_id=_choice(evidence_ids))
    return create_model(
        "ScopedRecommendReply",
        __base__=RecommendReply,
        immediate=(list[advice], Field(default_factory=list, max_length=5)),
        longer_term=(list[advice], Field(default_factory=list, max_length=5)),
        rewrites=(
            list[rewrite],
            Field(default_factory=list, max_length=5 if evidence_ids else 0),
        ),
    )


@dataclass(frozen=True, slots=True)
class Recommendation:
    requirement_id: str
    title: str
    detail: str


@dataclass(frozen=True, slots=True)
class Rewrite:
    evidence_id: str
    before: str
    after: str
    questions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Recommendations:
    immediate: tuple[Recommendation, ...]
    longer_term: tuple[Recommendation, ...]
    rewrites: tuple[Rewrite, ...]
    dropped: int


def rewritable_evidence(
    assessment: Assessment, evidence: Mapping[str, EvidenceItem]
) -> tuple[EvidenceItem, ...]:
    """CV items some requirement actually cited: the only text a rewrite may start from."""
    cited = dict.fromkeys(
        evidence_id for result in assessment.results for evidence_id in result.evidence_ids
    )
    return tuple(evidence[i] for i in cited if i in evidence and "cv" in evidence[i].sources)


def allowed_ids(assessment: Assessment) -> list[str]:
    return list(dict.fromkeys(result.requirement.id for result in assessment.results))


def _recommendations(
    items: list[RecommendationItem], allowed: set[str]
) -> tuple[tuple[Recommendation, ...], int]:
    kept = tuple(
        Recommendation(item.requirement_id, item.title.strip(), item.detail.strip())
        for item in items
        if item.requirement_id in allowed and item.title.strip()
    )
    return kept, len(items) - len(kept)


def _adds_numbers(before: str, after: str) -> bool:
    return not set(_NUMBER.findall(after)) <= set(_NUMBER.findall(before))


def _rewrites(
    items: list[RewriteItem], sources: Mapping[str, EvidenceItem]
) -> tuple[tuple[Rewrite, ...], int]:
    kept: dict[str, Rewrite] = {}
    for item in items:
        source = sources.get(item.evidence_id)
        after = item.after.strip()
        if source is not None:
            # The model sometimes echoes the prompt's entry header; the reader never wrote it.
            after = after.removeprefix(f"{source.section_label} ({source.kind})").strip()
        if source is None or item.evidence_id in kept or not after or after == source.text:
            continue
        # A number the evidence doesn't contain is an invented fact; it must be asked instead.
        if _adds_numbers(source.text, after):
            continue
        questions = tuple(q.strip() for q in item.questions if q.strip())
        kept[item.evidence_id] = Rewrite(item.evidence_id, source.text, after, questions)
    return tuple(kept.values()), len(items) - len(kept)


async def recommend(
    generator: Generator,
    title: str,
    assessment: Assessment,
    evidence: Mapping[str, EvidenceItem],
) -> Recommendations:
    sources = rewritable_evidence(assessment, evidence)
    messages = build_recommend_messages(
        title,
        [
            (
                result.requirement.id,
                result.requirement.importance,
                result.status,
                result.requirement.text,
                result.rationale,
            )
            for result in assessment.results
        ],
        sources,
    )
    allowed = {result.requirement.id for result in assessment.results}
    schema = reply_model(tuple(allowed_ids(assessment)), tuple(item.id for item in sources))
    reply = await generate_validated(generator, messages, schema, RECOMMEND_SAMPLING)
    immediate, dropped_now = _recommendations(reply.immediate, allowed)
    longer_term, dropped_later = _recommendations(reply.longer_term, allowed)
    rewrites, dropped_rewrites = _rewrites(reply.rewrites, {item.id: item for item in sources})
    return Recommendations(
        immediate=immediate,
        longer_term=longer_term,
        rewrites=rewrites,
        dropped=dropped_now + dropped_later + dropped_rewrites,
    )
