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
    # The enum only steers the model's grammar (given a free string, a local model answers "0"
    # for "req:required:0"); validation stays a plain string, so code still drops a bad id.
    # An empty enum is not a valid grammar, so with no ids the field is left open.
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


_MAGNITUDE = re.compile(r"\b\d+(?:[.,]\d+)?\s*(?:k|m|bn|b|x|%)(?![a-z])", re.IGNORECASE)
_QUANTITY_WORDS = frozenset(
    [
        "one",
        "two",
        "three",
        "four",
        "five",
        "six",
        "seven",
        "eight",
        "nine",
        "ten",
        "eleven",
        "twelve",
        "thirteen",
        "fourteen",
        "fifteen",
        "sixteen",
        "seventeen",
        "eighteen",
        "nineteen",
        "twenty",
        "thirty",
        "forty",
        "fifty",
        "sixty",
        "seventy",
        "eighty",
        "ninety",
        "hundred",
        "hundreds",
        "thousand",
        "thousands",
        "million",
        "millions",
        "billion",
        "billions",
        "dozen",
        "dozens",
        "half",
        "twice",
        "thrice",
        "double",
        "doubled",
        "doubling",
        "triple",
        "tripled",
        "tripling",
        "quadrupled",
        "tenfold",
    ]
)
_WORD = re.compile(r"[A-Za-z][A-Za-z0-9+#.]*[A-Za-z0-9+#]|[A-Za-z]")
_SENTENCE_START = re.compile(r"(?:^|[.!?;:]\s+)$")


def _names(text: str) -> list[tuple[str, bool]]:
    """Every word with whether it opens a sentence (where any word is capitalised)."""
    return [
        (match.group(), bool(_SENTENCE_START.search(text[: match.start()])))
        for match in _WORD.finditer(text)
    ]


def _is_name(word: str, opens_sentence: bool) -> bool:
    # A capital mid-sentence is a name; at a sentence start only an inner capital or a digit
    # ("PostgreSQL", "GraphQL", "AWS", "S3") marks one, since any first word is capitalised.
    if any(char.isdigit() for char in word) or sum(char.isupper() for char in word) > 1:
        return True
    return word[0].isupper() and not opens_sentence


def invents_facts(before: str, after: str) -> bool:
    """True when `after` states a number, quantity or name that `before` does not contain."""
    if not set(_NUMBER.findall(after)) <= set(_NUMBER.findall(before)):
        return True
    magnitude = {m.lower().replace(" ", "") for m in _MAGNITUDE.findall(after)}
    if not magnitude <= {m.lower().replace(" ", "") for m in _MAGNITUDE.findall(before)}:
        return True
    known = {word.lower() for word, _ in _names(before)}
    for word, opens_sentence in _names(after):
        lowered = word.lower()
        if lowered in known:
            continue
        if lowered in _QUANTITY_WORDS or _is_name(word, opens_sentence):
            return True
    return False


def _rewrites(
    items: list[RewriteItem], sources: Mapping[str, EvidenceItem]
) -> tuple[tuple[Rewrite, ...], int]:
    kept: dict[str, Rewrite] = {}
    for item in items:
        source = sources.get(item.evidence_id)
        after = item.after.strip()
        if source is not None:
            # The model sometimes echoes the prompt's entry header, "[id] label (kind)"; the
            # reader never wrote it.
            after = after.removeprefix(f"[{source.id}]").strip()
            after = after.removeprefix(f"{source.section_label} ({source.kind})").strip()
        if source is None or item.evidence_id in kept or not after or after == source.text:
            continue
        # A number, quantity or name the evidence doesn't contain is invented; ask instead.
        if invents_facts(source.text, after):
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
