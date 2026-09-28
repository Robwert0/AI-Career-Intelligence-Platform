import pytest
from fakes import KeywordEmbedder

from app.ai.match.preselect import NO_SIMILARITY, evidence_text, preselect
from app.ai.match.requirements import RequirementRef, requirement_refs
from app.ai.match.schemas import EvidenceItem, EvidenceKind, JobPosting, Requirement


def item(index: int, text: str, kind: EvidenceKind = "work") -> EvidenceItem:
    return EvidenceItem(
        id=f"cv:experience:{index}",
        sources=("cv",),
        kind=kind,
        section_label="Experience · Acme",
        text=text,
    )


def ref(index: int, text: str) -> RequirementRef:
    return RequirementRef(
        id=f"req:required:{index}", text=text, importance="required", sensitive=False
    )


EVIDENCE = [
    item(0, "Built Go services on PostgreSQL"),
    item(1, "Streamed events through Kafka with Go"),
    item(2, "Built a React dashboard"),
]


def test_each_requirement_gets_its_most_similar_evidence_first() -> None:
    selection = preselect([ref(0, "Kafka"), ref(1, "React")], EVIDENCE, KeywordEmbedder(), top_k=2)

    assert selection.ids_for("req:required:0")[0] == "cv:experience:1"
    assert selection.ids_for("req:required:1")[0] == "cv:experience:2"


def test_top_k_caps_the_candidates() -> None:
    selection = preselect([ref(0, "Go")], EVIDENCE, KeywordEmbedder(), top_k=2)

    assert len(selection.candidates["req:required:0"]) == 2


def test_ties_keep_evidence_order() -> None:
    selection = preselect([ref(0, "nursing")], EVIDENCE, KeywordEmbedder(), top_k=3)

    assert selection.ids_for("req:required:0") == (
        "cv:experience:0",
        "cv:experience:1",
        "cv:experience:2",
    )


def test_the_best_similarity_spans_every_pair() -> None:
    selection = preselect(
        [ref(0, "nursing"), ref(1, "React")], EVIDENCE, KeywordEmbedder(), top_k=1
    )

    assert selection.best_similarity == pytest.approx(1.0)


def test_unrelated_sources_have_no_similarity() -> None:
    selection = preselect([ref(0, "nursing")], EVIDENCE, KeywordEmbedder(), top_k=1)

    assert selection.best_similarity == pytest.approx(0.0)


def test_requirements_are_queries_and_evidence_is_embedded_once() -> None:
    embedder = KeywordEmbedder()

    preselect([ref(0, "Go"), ref(1, "Kafka")], EVIDENCE, embedder, top_k=1)

    assert embedder.queries == ["Go", "Kafka"]
    assert embedder.documents == [evidence_text(e) for e in EVIDENCE]


def test_no_evidence_means_no_candidates() -> None:
    selection = preselect([ref(0, "Go")], [], KeywordEmbedder(), top_k=8)

    assert selection.candidates == {"req:required:0": ()}
    assert selection.best_similarity == NO_SIMILARITY


def test_requirement_ids_follow_the_posting_order() -> None:
    posting = JobPosting(
        title="Backend Engineer",
        required=[
            Requirement(text="Go", sensitive=False),
            Requirement(text="EU work permit", sensitive=True),
        ],
        preferred=[Requirement(text="Kafka", sensitive=False)],
    )

    refs = requirement_refs(posting)

    assert [(r.id, r.importance, r.sensitive) for r in refs] == [
        ("req:required:0", "required", False),
        ("req:required:1", "required", True),
        ("req:preferred:0", "preferred", False),
    ]
