import uuid

import pytest
from fakes import FakeEmbedder
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.retriever import (
    RANK_WINDOW_MULTIPLIER,
    EmptyQueryError,
    QueryTooLongError,
    Retriever,
    reciprocal_rank_fusion,
)
from app.ai.tokenizer import token_budget
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
        self, embedding: list[float], limit: int, section: str | None = None
    ) -> list[Chunk]:
        self.limits.append(limit)
        return await super().search_by_vector(embedding, limit, section)

    async def search_by_text(
        self, text: str, limit: int, section: str | None = None
    ) -> list[Chunk]:
        self.limits.append(limit)
        return await super().search_by_text(text, limit, section)


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
        await retriever.retrieve(query)


async def test_a_query_past_the_token_budget_is_rejected_rather_than_truncated(
    retriever: Retriever,
) -> None:
    with pytest.raises(QueryTooLongError):
        await retriever.retrieve("kubernetes " * (token_budget() + 1))


async def test_each_leg_is_searched_wider_than_the_final_limit(
    retriever: Retriever, recording_repo: RecordingRepository
) -> None:
    await retriever.retrieve("kubernetes", limit=2)
    assert recording_repo.limits == [2 * RANK_WINDOW_MULTIPLIER] * 2


async def test_retrieve_returns_no_more_than_the_limit(retriever: Retriever) -> None:
    assert len(await retriever.retrieve("engineer kubernetes", limit=2)) <= 2


async def test_retrieve_still_answers_when_the_text_leg_finds_nothing(
    retriever: Retriever,
) -> None:
    assert await retriever.retrieve("zzzznonexistenttoken") != []


async def test_retrieve_can_narrow_to_one_section(retriever: Retriever) -> None:
    hits = await retriever.retrieve("engineer kubernetes", section="skills")
    assert [hit.section for hit in hits] == ["skills"]
