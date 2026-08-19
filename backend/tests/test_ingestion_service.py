import uuid
from pathlib import Path

import pytest
from fakes import FakeEmbedder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Chunk
from app.repositories import ChunkRepository
from app.services.ingestion_service import EmptyDocumentError, IngestionService

FIXTURES = Path(__file__).parent / "fixtures"
CV_PDF = (FIXTURES / "a_titlecase.pdf").read_bytes()
DOCUMENT_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")


def service(session: AsyncSession) -> IngestionService:
    return IngestionService(ChunkRepository(session), FakeEmbedder())


async def stored(session: AsyncSession, document_id: uuid.UUID) -> list[Chunk]:
    result = await session.execute(
        select(Chunk).where(Chunk.document_id == document_id).order_by(Chunk.chunk_index)
    )
    return list(result.scalars())


async def test_ingest_writes_one_row_per_chunk_and_returns_the_count(
    db_session: AsyncSession,
) -> None:
    written = await service(db_session).ingest(CV_PDF, DOCUMENT_ID)
    rows = await stored(db_session, DOCUMENT_ID)
    assert written == len(rows)
    assert written > 0


async def test_reingesting_the_same_document_replaces_rather_than_duplicates(
    db_session: AsyncSession,
) -> None:
    first = await service(db_session).ingest(CV_PDF, DOCUMENT_ID)
    second = await service(db_session).ingest(CV_PDF, DOCUMENT_ID)
    rows = await stored(db_session, DOCUMENT_ID)
    assert first == second == len(rows)
    indices = [row.chunk_index for row in rows]
    assert indices == sorted(set(indices))


async def test_ingest_leaves_other_documents_untouched(db_session: AsyncSession) -> None:
    other = uuid.uuid4()
    written = await service(db_session).ingest(CV_PDF, other)
    await service(db_session).ingest(CV_PDF, DOCUMENT_ID)
    assert [row.chunk_index for row in await stored(db_session, other)] == list(range(written))


async def test_every_row_is_stamped_with_the_embedder_that_produced_it(
    db_session: AsyncSession,
) -> None:
    await service(db_session).ingest(CV_PDF, DOCUMENT_ID)
    rows = await stored(db_session, DOCUMENT_ID)
    assert {row.embedding_model for row in rows} == {FakeEmbedder().model_name}


async def test_each_row_keeps_the_vector_that_belongs_to_its_own_text(
    db_session: AsyncSession,
) -> None:
    embedder = FakeEmbedder()
    await IngestionService(ChunkRepository(db_session), embedder).ingest(CV_PDF, DOCUMENT_ID)
    for row in await stored(db_session, DOCUMENT_ID):
        assert list(row.embedding) == pytest.approx(embedder.embed_query(row.content))


async def test_a_document_that_chunks_to_nothing_is_rejected(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.services.ingestion_service.pdf_to_markdown", lambda _: "")
    with pytest.raises(EmptyDocumentError):
        await service(db_session).ingest(CV_PDF, DOCUMENT_ID)


async def test_a_rejected_reingest_leaves_the_previous_chunks_intact(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    await service(db_session).ingest(CV_PDF, DOCUMENT_ID)
    before = await stored(db_session, DOCUMENT_ID)

    monkeypatch.setattr("app.services.ingestion_service.pdf_to_markdown", lambda _: "")
    with pytest.raises(EmptyDocumentError):
        await service(db_session).ingest(CV_PDF, DOCUMENT_ID)

    after = await stored(db_session, DOCUMENT_ID)
    assert [row.chunk_index for row in after] == [row.chunk_index for row in before]
