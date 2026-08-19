import math
from pathlib import Path

import pytest
from fakes import FakeEmbedder

from app.ai.chunking import chunk_cv
from app.ai.embeddings import BgeEmbedder, Embedder
from app.core.config import settings

FIXTURES = Path(__file__).parent / "fixtures"


def norm(vector: list[float]) -> float:
    return math.sqrt(sum(value * value for value in vector))


@pytest.fixture(scope="module")
def bge() -> BgeEmbedder:
    return BgeEmbedder()


@pytest.fixture(scope="module")
def cv_chunks() -> list[str]:
    return [chunk.content for chunk in chunk_cv((FIXTURES / "sample_cv.md").read_text())]


def test_both_embedders_satisfy_the_embedder_protocol(bge: BgeEmbedder) -> None:
    embedders: list[Embedder] = [FakeEmbedder(), bge]
    assert [embedder.dimensions for embedder in embedders] == [settings.embedding_dim] * 2


def test_the_fake_returns_the_same_vector_for_the_same_text() -> None:
    assert FakeEmbedder().embed_query("python") == FakeEmbedder().embed_query("python")


def test_the_fake_returns_different_vectors_for_different_texts() -> None:
    assert FakeEmbedder().embed_query("python") != FakeEmbedder().embed_query("postgres")


@pytest.mark.parametrize("embedder_name", ["fake", "bge"])
def test_vectors_are_unit_length(embedder_name: str, bge: BgeEmbedder) -> None:
    embedder: Embedder = FakeEmbedder() if embedder_name == "fake" else bge
    for vector in embedder.embed_documents(["alpha", "beta"]):
        assert norm(vector) == pytest.approx(1.0)
    assert norm(embedder.embed_query("alpha")) == pytest.approx(1.0)


@pytest.mark.parametrize("embedder_name", ["fake", "bge"])
def test_vectors_match_the_configured_dimension(embedder_name: str, bge: BgeEmbedder) -> None:
    embedder: Embedder = FakeEmbedder() if embedder_name == "fake" else bge
    assert all(len(v) == settings.embedding_dim for v in embedder.embed_documents(["a", "b"]))
    assert len(embedder.embed_query("a")) == settings.embedding_dim


@pytest.mark.parametrize("embedder_name", ["fake", "bge"])
def test_embed_documents_returns_one_vector_per_text_in_order(
    embedder_name: str, bge: BgeEmbedder
) -> None:
    embedder: Embedder = FakeEmbedder() if embedder_name == "fake" else bge
    texts = ["alpha", "beta", "gamma"]
    vectors = embedder.embed_documents(texts)
    assert len(vectors) == len(texts)
    assert vectors[1] == pytest.approx(embedder.embed_documents(["beta"])[0], abs=1e-6)


@pytest.mark.parametrize("embedder_name", ["fake", "bge"])
def test_embed_query_returns_a_flat_vector_not_a_batch(
    embedder_name: str, bge: BgeEmbedder
) -> None:
    embedder: Embedder = FakeEmbedder() if embedder_name == "fake" else bge
    vector = embedder.embed_query("alpha")
    assert len(vector) == settings.embedding_dim
    assert all(isinstance(value, float) for value in vector)


def test_the_query_prefix_is_applied(bge: BgeEmbedder) -> None:
    text = "kubernetes"
    assert bge.embed_query(text) != bge.embed_documents([text])[0]


@pytest.mark.parametrize("embedder_name", ["fake", "bge"])
def test_embedding_no_documents_returns_no_vectors(embedder_name: str, bge: BgeEmbedder) -> None:
    embedder: Embedder = FakeEmbedder() if embedder_name == "fake" else bge
    assert embedder.embed_documents([]) == []


def test_the_model_name_records_the_pinned_revision(bge: BgeEmbedder) -> None:
    assert bge.model_name == f"{settings.embedding_model}@{settings.embedding_model_revision}"


def test_the_real_embedder_ranks_by_meaning_not_keywords(
    bge: BgeEmbedder, cv_chunks: list[str]
) -> None:
    chunks = chunk_cv((FIXTURES / "sample_cv.md").read_text())
    vectors = dict(zip((c.section for c in chunks), bge.embed_documents(cv_chunks), strict=True))
    query = bge.embed_query("What did this person study at university?")

    def similarity(section: str) -> float:
        return sum(a * b for a, b in zip(vectors[section], query, strict=True))

    assert similarity("education") > similarity("experience") + 0.05
