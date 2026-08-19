import uuid

import pytest
from fakes import FakeEmbedder
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings import QueryTooLongError
from app.ai.retriever import (
    MAX_LIMIT,
    MAX_QUERY_CHARS,
    RANK_WINDOW_MULTIPLIER,
    EmptyQueryError,
    Retriever,
    reciprocal_rank_fusion,
)
from app.models import Chunk
from app.repositories import ChunkRepository

DOCUMENT_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")

SEED = [
    ("experience", "Senior backend engineer building Go services at Acme."),
    ("skills", "Kubernetes, Terraform, PostgreSQL and Redis."),
    ("education", "BSc Computer Science, Leeds."),
    ("summary", "Ten years shipping distributed systems."),
]


def chunk(section: str) -> Chunk:
    return Chunk(
        id=uuid.uuid4(),
        document_id=DOCUMENT_ID,
        chunk_index=0,
        content=section,
        section=section,
        embedding=[0.0],
        embedding_model="fake",
    )


def test_a_chunk_ranked_in_both_legs_beats_one_ranked_first_in_only_one() -> None:
    both, one_leg = chunk("both"), chunk("one_leg")
    fused = reciprocal_rank_fusion([[one_leg, both], [both]])
    assert [c.section for c in fused] == ["both", "one_leg"]


def test_the_same_chunk_from_two_legs_appears_once() -> None:
    only = chunk("only")
    assert len(reciprocal_rank_fusion([[only], [only]])) == 1


def test_a_chunk_found_by_a_single_leg_is_still_a_candidate() -> None:
    a, b = chunk("a"), chunk("b")
    assert {c.section for c in reciprocal_rank_fusion([[a], [b]])} == {"a", "b"}


def test_rank_order_within_a_leg_is_preserved() -> None:
    first, second = chunk("first"), chunk("second")
    assert [c.section for c in reciprocal_rank_fusion([[first, second]])] == ["first", "second"]


def test_fusion_returns_at_most_the_limit() -> None:
    chunks = [chunk(f"c{i}") for i in range(10)]
    assert len(reciprocal_rank_fusion([chunks], limit=3)) == 3


def test_an_empty_leg_degrades_to_the_other_one() -> None:
    a, b = chunk("a"), chunk("b")
    assert [c.section for c in reciprocal_rank_fusion([[a, b], []])] == ["a", "b"]


class RecordingRepository(ChunkRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self.limits: list[int] = []

    async def search_by_vector(
        self,
        embedding: list[float],
        limit: int,
        section: str | None = None,
        document_id: uuid.UUID | None = None,
    ) -> list[Chunk]:
        self.limits.append(limit)
        return await super().search_by_vector(embedding, limit, section, document_id)

    async def search_by_text(
        self,
        query: str,
        limit: int,
        section: str | None = None,
        document_id: uuid.UUID | None = None,
    ) -> list[Chunk]:
        self.limits.append(limit)
        return await super().search_by_text(query, limit, section, document_id)


@pytest.fixture
async def recording_repo(db_session: AsyncSession) -> RecordingRepository:
    embedder = FakeEmbedder()
    vectors = embedder.embed_documents([content for _, content in SEED])
    chunks = [
        Chunk(
            document_id=DOCUMENT_ID,
            chunk_index=index,
            content=content,
            section=section,
            embedding=vector,
            embedding_model=embedder.model_name,
        )
        for index, ((section, content), vector) in enumerate(zip(SEED, vectors, strict=True))
    ]
    repo = RecordingRepository(db_session)
    await repo.replace_document_chunks(DOCUMENT_ID, chunks)
    return repo


@pytest.fixture
def retriever(recording_repo: RecordingRepository) -> Retriever:
    return Retriever(recording_repo, FakeEmbedder())


@pytest.mark.parametrize("query", ["", "   ", "\n\t "])
async def test_a_query_with_no_searchable_text_is_rejected(
    retriever: Retriever, query: str
) -> None:
    with pytest.raises(EmptyQueryError):
        await retriever.retrieve(query, document_id=None)


async def test_a_query_past_the_character_cap_is_rejected_before_anything_scans_it(
    retriever: Retriever,
) -> None:
    with pytest.raises(QueryTooLongError):
        await retriever.retrieve("k" * (MAX_QUERY_CHARS + 1), document_id=None)


@pytest.mark.parametrize("limit", [0, -1, MAX_LIMIT + 1])
async def test_an_out_of_range_limit_is_rejected(retriever: Retriever, limit: int) -> None:
    with pytest.raises(ValueError):
        await retriever.retrieve("kubernetes", document_id=None, limit=limit)


async def test_retrieve_can_narrow_to_one_document(
    retriever: Retriever, recording_repo: RecordingRepository
) -> None:
    other = uuid.uuid4()
    assert await retriever.retrieve("kubernetes", document_id=other) == []
    assert await retriever.retrieve("kubernetes", document_id=DOCUMENT_ID) != []


def test_fusion_rejects_a_chunk_that_was_never_persisted() -> None:
    transient = Chunk(
        document_id=DOCUMENT_ID,
        chunk_index=0,
        content="x",
        section="skills",
        embedding=[0.0],
        embedding_model="fake",
    )
    with pytest.raises(ValueError):
        reciprocal_rank_fusion([[transient]])


@pytest.mark.parametrize(("k", "limit"), [(0, 5), (-1, 5), (60, 0), (60, -1)])
def test_fusion_rejects_out_of_range_parameters(k: int, limit: int) -> None:
    with pytest.raises(ValueError):
        reciprocal_rank_fusion([[chunk("a")]], k=k, limit=limit)


async def test_each_leg_is_searched_wider_than_the_final_limit(
    retriever: Retriever, recording_repo: RecordingRepository
) -> None:
    await retriever.retrieve("kubernetes", document_id=None, limit=2)
    assert recording_repo.limits == [2 * RANK_WINDOW_MULTIPLIER] * 2


async def test_retrieve_returns_no_more_than_the_limit(retriever: Retriever) -> None:
    assert len(await retriever.retrieve("engineer kubernetes", document_id=None, limit=2)) <= 2


async def test_retrieve_still_answers_when_the_text_leg_finds_nothing(
    retriever: Retriever,
) -> None:
    assert await retriever.retrieve("zzzznonexistenttoken", document_id=None) != []


async def test_retrieve_can_narrow_to_one_section(retriever: Retriever) -> None:
    hits = await retriever.retrieve("engineer kubernetes", document_id=None, section="skills")
    assert [hit.section for hit in hits] == ["skills"]
