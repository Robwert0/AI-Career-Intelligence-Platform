import uuid
from typing import Any

from sqlalchemy import ColumnElement, cast, delete, func, select, text
from sqlalchemy.dialects.postgresql import TSQUERY
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Chunk

TEXT_SEARCH_CONFIG = "english"


def _any_word_tsquery(query: str) -> ColumnElement[Any]:
    lexemes = func.tsvector_to_array(func.to_tsvector(TEXT_SEARCH_CONFIG, query))
    lexeme = func.unnest(lexemes).column_valued("lexeme")
    ored = select(
        func.array_to_string(func.array_agg(func.quote_literal(lexeme)), " | ")
    ).scalar_subquery()
    return cast(ored, TSQUERY)


class ChunkRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def replace_document_chunks(self, document_id: uuid.UUID, chunks: list[Chunk]) -> int:
        await self._session.execute(delete(Chunk).where(Chunk.document_id == document_id))
        self._session.add_all(chunks)
        await self._session.flush()

        return len(chunks)

    async def search_by_vector(
        self,
        embedding: list[float],
        limit: int,
        section: str | None = None,
        document_id: uuid.UUID | None = None,
    ) -> list[Chunk]:
        if section is not None or document_id is not None:
            await self._session.execute(text("SET LOCAL hnsw.iterative_scan = 'relaxed_order'"))

        distance = Chunk.embedding.cosine_distance(embedding)
        stmt = select(Chunk).order_by(distance).limit(limit)

        if section is not None:
            stmt = stmt.where(Chunk.section == section)
        if document_id is not None:
            stmt = stmt.where(Chunk.document_id == document_id)

        result = await self._session.execute(stmt)

        return list(result.scalars())

    async def search_by_text(
        self,
        query: str,
        limit: int,
        section: str | None = None,
        document_id: uuid.UUID | None = None,
    ) -> list[Chunk]:
        tsquery = _any_word_tsquery(query)
        rank = func.ts_rank(Chunk.search_vector, tsquery).desc()

        stmt = (
            select(Chunk).where(Chunk.search_vector.op("@@")(tsquery)).order_by(rank).limit(limit)
        )
        if section is not None:
            stmt = stmt.where(Chunk.section == section)
        if document_id is not None:
            stmt = stmt.where(Chunk.document_id == document_id)

        result = await self._session.execute(stmt)

        return list(result.scalars())
