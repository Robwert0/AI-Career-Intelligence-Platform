import uuid
from typing import cast

import pytest
from pgvector.sqlalchemy import Vector
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.sections import SECTIONS
from app.models import Chunk

MODEL = "bge-small-en-v1.5"


def unit_vector(axis: int) -> list[float]:
    vector = [0.0] * 384
    vector[axis] = 1.0
    return vector


async def add_chunk(
    db_session: AsyncSession,
    content: str,
    *,
    document_id: uuid.UUID | None = None,
    chunk_index: int = 0,
    section: str = "experience",
    axis: int = 0,
    embedding: list[float] | None = None,
) -> Chunk:
    chunk = Chunk(
        document_id=document_id or uuid.uuid4(),
        chunk_index=chunk_index,
        content=content,
        section=section,
        embedding=unit_vector(axis) if embedding is None else embedding,
        embedding_model=MODEL,
    )
    db_session.add(chunk)
    await db_session.flush()
    await db_session.refresh(chunk)
    return chunk


async def test_search_vector_is_generated_from_content(db_session: AsyncSession) -> None:
    chunk = await add_chunk(db_session, "Built async FastAPI backends")

    # "backends" stored as "backend" proves Postgres stemmed it, not that we copied the string.
    assert "'backend'" in chunk.search_vector
    assert "'fastapi'" in chunk.search_vector


async def test_search_vector_follows_a_content_update(db_session: AsyncSession) -> None:
    chunk = await add_chunk(db_session, "Kubernetes cluster administration")

    chunk.content = "Terraform module authoring"
    await db_session.flush()
    await db_session.refresh(chunk)

    assert "'terraform'" in chunk.search_vector
    assert "kubernetes" not in chunk.search_vector


async def test_full_text_search_matches_a_stemmed_query(db_session: AsyncSession) -> None:
    document_id = uuid.uuid4()
    await add_chunk(db_session, "Built async FastAPI backends", document_id=document_id)
    await add_chunk(db_session, "Kubernetes and Helm", document_id=document_id, chunk_index=1)

    matched = (
        (
            await db_session.execute(
                select(Chunk.content)
                .where(Chunk.document_id == document_id)
                .where(text("search_vector @@ plainto_tsquery('english', :q)"))
                .params(q="backend")
            )
        )
        .scalars()
        .all()
    )

    # Query "backend" finds content saying "backends" — the index stores stems, not literals.
    assert matched == ["Built async FastAPI backends"]


async def test_hybrid_query_combines_vector_fts_and_section(db_session: AsyncSession) -> None:
    document_id = uuid.uuid4()
    await add_chunk(
        db_session, "Python backend services", document_id=document_id, section="experience", axis=0
    )
    await add_chunk(
        db_session,
        "Python backend hobby project",
        document_id=document_id,
        chunk_index=1,
        section="projects",
        axis=0,
    )

    found = (
        (
            await db_session.execute(
                select(Chunk.content)
                .where(Chunk.document_id == document_id)
                .where(Chunk.section == "experience")
                .where(text("search_vector @@ plainto_tsquery('english', :q)"))
                .params(q="backend")
                .order_by(Chunk.embedding.cosine_distance(unit_vector(0)))
            )
        )
        .scalars()
        .all()
    )

    # Both rows match the vector and the text; only the section filter separates them.
    assert found == ["Python backend services"]


async def test_cosine_distance_orders_by_similarity(db_session: AsyncSession) -> None:
    document_id = uuid.uuid4()
    await add_chunk(db_session, "on axis zero", document_id=document_id, axis=0)
    await add_chunk(db_session, "on axis five", document_id=document_id, chunk_index=1, axis=5)

    query = unit_vector(5)
    ordered = (
        await db_session.execute(
            select(Chunk.content, Chunk.embedding.cosine_distance(query).label("distance"))
            .where(Chunk.document_id == document_id)
            .order_by("distance")
        )
    ).all()

    assert [row.content for row in ordered] == ["on axis five", "on axis zero"]
    assert ordered[0].distance == 0.0
    assert ordered[1].distance == 1.0


async def test_a_zero_embedding_is_rejected(db_session: AsyncSession) -> None:
    # An empty or failed embedding call returns zeros; cosine distance against it is NaN, which
    # Postgres sorts last, so such a chunk would be silently unretrievable forever.
    with pytest.raises(IntegrityError, match="ck_chunks_embedding_nonzero"):
        await add_chunk(db_session, "failed embedding", embedding=[0.0] * 384)


async def test_an_unknown_section_is_rejected(db_session: AsyncSession) -> None:
    with pytest.raises(IntegrityError, match="ck_chunks_section"):
        await add_chunk(db_session, "typo", section="experince")


async def test_every_declared_section_is_accepted(db_session: AsyncSession) -> None:
    document_id = uuid.uuid4()
    for index, section in enumerate(SECTIONS):
        await add_chunk(
            db_session, section, document_id=document_id, chunk_index=index, section=section
        )

    stored = (
        (await db_session.execute(select(Chunk.section).where(Chunk.document_id == document_id)))
        .scalars()
        .all()
    )
    assert sorted(stored) == sorted(SECTIONS)


async def test_reingesting_the_same_position_is_rejected(db_session: AsyncSession) -> None:
    # Re-ingestion must replace a document's chunks, never silently accumulate a second copy.
    document_id = uuid.uuid4()
    await add_chunk(db_session, "first pass", document_id=document_id, chunk_index=0)

    with pytest.raises(IntegrityError, match="uq_chunks_document_id_chunk_index"):
        await add_chunk(db_session, "second pass", document_id=document_id, chunk_index=0)


async def test_cosine_ordering_is_served_by_the_hnsw_index(db_session: AsyncSession) -> None:
    # The index is built with vector_cosine_ops, so only the <=> operator can use it. Querying
    # with <-> or <#> still returns correct rows via a sequential scan — a silent performance
    # regression no result-based assertion could ever catch. This pins the opclass to the
    # operator that cosine_distance() emits.
    document_id = uuid.uuid4()
    for index in range(60):
        await add_chunk(
            db_session, f"chunk {index}", document_id=document_id, chunk_index=index, axis=index
        )

    await db_session.execute(text("SET LOCAL enable_seqscan = off"))
    plan = (
        (
            await db_session.execute(
                text(
                    "EXPLAIN SELECT content FROM chunks "
                    "ORDER BY embedding <=> cast(:q as vector) LIMIT 5"
                ).params(q=str(unit_vector(3)))
            )
        )
        .scalars()
        .all()
    )

    assert any("ix_chunks_embedding_hnsw" in line for line in plan), plan


async def test_the_stored_dimension_matches_the_configured_embedding_dim() -> None:
    # The column width is fixed at DDL time; config drifting from it means every write fails.
    column_type = cast(Vector, Chunk.__table__.c.embedding.type)
    assert column_type.dim == settings.embedding_dim
