from collections.abc import Sequence
from dataclasses import dataclass, field

from app.ai.embeddings import Embedder
from app.ai.match.requirements import RequirementRef
from app.ai.match.schemas import EvidenceItem

NO_SIMILARITY = -1.0


@dataclass(frozen=True, slots=True)
class Candidate:
    evidence_id: str
    similarity: float


@dataclass(frozen=True, slots=True)
class Preselection:
    candidates: dict[str, tuple[Candidate, ...]]
    best_similarity: float
    # Per source: the mean over requirements of that requirement's best match. The refusal gate
    # uses it because one lucky pair ("Excel" in an accountant posting) made a best-pair gate
    # barely separate related from unrelated postings.
    relatedness: dict[str, float] = field(default_factory=dict)

    def ids_for(self, requirement_id: str) -> tuple[str, ...]:
        return tuple(candidate.evidence_id for candidate in self.candidates[requirement_id])


def evidence_text(item: EvidenceItem) -> str:
    return f"{item.section_label}: {item.text}"


def source_of(item: EvidenceItem) -> str:
    # A CV project merged with its repo is CV prose, so it is judged like the CV.
    return "cv" if "cv" in item.sources else "github"


def _dot(a: Sequence[float], b: Sequence[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


def preselect(
    requirements: Sequence[RequirementRef],
    evidence: Sequence[EvidenceItem],
    embedder: Embedder,
    *,
    top_k: int,
) -> Preselection:
    if not requirements or not evidence:
        return Preselection({req.id: () for req in requirements}, NO_SIMILARITY)
    # Asymmetric model: requirements are the queries, evidence the passages.
    vectors = embedder.embed_documents([evidence_text(item) for item in evidence])
    candidates: dict[str, tuple[Candidate, ...]] = {}
    best = NO_SIMILARITY
    per_source: dict[str, list[float]] = {}
    for requirement in requirements:
        query = embedder.embed_query(requirement.text)
        # Normalised vectors, so the dot product is the cosine similarity.
        scored = [
            Candidate(item.id, _dot(query, vector))
            for item, vector in zip(evidence, vectors, strict=True)
        ]
        # sorted() is stable, so ties keep evidence order and the result is reproducible.
        ranked = sorted(scored, key=lambda candidate: candidate.similarity, reverse=True)
        candidates[requirement.id] = tuple(ranked[:top_k])
        best = max(best, ranked[0].similarity)
        best_here: dict[str, float] = {}
        for item, candidate in zip(evidence, scored, strict=True):
            source = source_of(item)
            best_here[source] = max(best_here.get(source, NO_SIMILARITY), candidate.similarity)
        for source, value in best_here.items():
            per_source.setdefault(source, []).append(value)
    relatedness = {source: sum(values) / len(values) for source, values in per_source.items()}
    return Preselection(candidates, best, relatedness)
