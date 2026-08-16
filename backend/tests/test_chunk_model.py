import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

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
    section: str = "experience",
    axis: int = 0,
) -> Chunk:
    chunk = Chunk(
        document_id=document_id or uuid.uuid4(),
        content=content,
        section=section,
        embedding=unit_vector(axis),
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


async def test_deleting_by_document_id_leaves_other_documents_intact(
    db_session: AsyncSession,
) -> None:
    stale, current = uuid.uuid4(), uuid.uuid4()
    await add_chunk(db_session, "old experience", document_id=stale)
    await add_chunk(db_session, "old skills", document_id=stale, section="skills")
    await add_chunk(db_session, "other document", document_id=current)

    await db_session.execute(delete(Chunk).where(Chunk.document_id == stale))

    remaining = (await db_session.execute(select(Chunk))).scalars().all()
    assert [chunk.document_id for chunk in remaining] == [current]


async def test_cosine_distance_orders_by_similarity(db_session: AsyncSession) -> None:
    document_id = uuid.uuid4()
    await add_chunk(db_session, "on axis zero", document_id=document_id, axis=0)
    await add_chunk(db_session, "on axis five", document_id=document_id, axis=5)

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
