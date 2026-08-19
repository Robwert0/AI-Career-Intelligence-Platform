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
    probe = vector_for(SEED[2][1])
    embedder = FakeEmbedder()

    def distance(content: str) -> float:
        vector = embedder.embed_query(content)
        return 1.0 - sum(a * b for a, b in zip(vector, probe, strict=True))

    expected = [content for _, content in sorted(SEED, key=lambda row: distance(row[1]))]
    hits = await seeded.search_by_vector(probe, limit=4)
    assert [hit.content for hit in hits] == expected


async def test_vector_search_can_narrow_to_one_document(
    seeded: ChunkRepository, db_session: AsyncSession
) -> None:
    other = uuid.uuid4()
    embedder = FakeEmbedder()
    await seeded.replace_document_chunks(
        other,
        [
            Chunk(
                document_id=other,
                chunk_index=0,
                content="Unrelated document about gardening.",
                section="other",
                embedding=embedder.embed_documents(["Unrelated document about gardening."])[0],
                embedding_model=embedder.model_name,
            )
        ],
    )
    hits = await seeded.search_by_vector(vector_for("anything"), limit=10, document_id=other)
    assert [hit.document_id for hit in hits] == [other]


async def test_text_search_can_narrow_to_one_document(seeded: ChunkRepository) -> None:
    assert await seeded.search_by_text("Terraform", limit=4, document_id=uuid.uuid4()) == []
    assert await seeded.search_by_text("Terraform", limit=4, document_id=DOCUMENT_ID) != []


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


@pytest.mark.parametrize(
    "query",
    [
        "our api runs at example.com:8080",
        "see ftp://x.com:21/readme",
        "ping x@y.com:99",
        "db.internal:5432/app",
        "docs at http://a.com/p!q",
        "docs at http://a.com/p(q)",
        "see http://a.com/p?x=1&y=2",
        "http://x.com/a:*",
    ],
)
async def test_punctuation_inside_a_url_lexeme_stays_literal(
    seeded: ChunkRepository, query: str
) -> None:
    assert await seeded.search_by_text(query, limit=4) == []


async def test_a_query_of_only_stopwords_is_not_an_error(seeded: ChunkRepository) -> None:
    assert await seeded.search_by_text("the and or of", limit=4) == []
