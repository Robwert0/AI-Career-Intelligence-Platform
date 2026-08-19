import uuid

import pytest
from fakes import FakeEmbedder
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Chunk
from app.repositories import ChunkRepository

DOCUMENT_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")

SEED = [
    ("experience", "Senior backend engineer building Go services at Acme."),
    ("skills", "Kubernetes, Terraform, PostgreSQL and Redis."),
    ("education", "BSc Computer Science, Leeds."),
    ("summary", "Ten years shipping distributed systems."),
]


@pytest.fixture
async def seeded(db_session: AsyncSession) -> ChunkRepository:
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
    repo = ChunkRepository(db_session)
    await repo.replace_document_chunks(DOCUMENT_ID, chunks)
    return repo


def vector_for(content: str) -> list[float]:
    return FakeEmbedder().embed_query(content)


async def test_vector_search_puts_the_exact_match_first(seeded: ChunkRepository) -> None:
    hits = await seeded.search_by_vector(vector_for(SEED[2][1]), limit=4)
    assert hits[0].content == SEED[2][1]


async def test_vector_search_orders_by_ascending_distance(seeded: ChunkRepository) -> None:
    hits = await seeded.search_by_vector(vector_for(SEED[0][1]), limit=4)
    assert hits[0].content == SEED[0][1]
    assert hits[-1].content != SEED[0][1]


async def test_vector_search_respects_the_limit(seeded: ChunkRepository) -> None:
    assert len(await seeded.search_by_vector(vector_for("anything"), limit=2)) == 2


async def test_vector_search_can_narrow_to_one_section(seeded: ChunkRepository) -> None:
    hits = await seeded.search_by_vector(vector_for("anything"), limit=4, section="skills")
    assert [hit.section for hit in hits] == ["skills"]


async def test_text_search_matches_a_stemmed_word(seeded: ChunkRepository) -> None:
    hits = await seeded.search_by_text("engineers", limit=4)
    assert [hit.section for hit in hits] == ["experience"]


async def test_text_search_finds_a_rare_exact_token(seeded: ChunkRepository) -> None:
    hits = await seeded.search_by_text("Terraform", limit=4)
    assert [hit.section for hit in hits] == ["skills"]


async def test_text_search_returns_nothing_without_lexical_overlap(
    seeded: ChunkRepository,
) -> None:
    assert await seeded.search_by_text("cloud infrastructure", limit=4) == []


async def test_text_search_accepts_raw_punctuation_from_a_user(seeded: ChunkRepository) -> None:
    hits = await seeded.search_by_text("does he know Kubernetes?", limit=4)
    assert [hit.section for hit in hits] == ["skills"]


async def test_text_search_can_narrow_to_one_section(seeded: ChunkRepository) -> None:
    assert await seeded.search_by_text("Kubernetes", limit=4, section="education") == []
