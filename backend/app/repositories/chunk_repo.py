import uuid
from typing import Any

from sqlalchemy import ColumnElement, cast, delete, func, select
from sqlalchemy.dialects.postgresql import TSQUERY
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Chunk

TEXT_SEARCH_CONFIG = "english"


def _any_word_tsquery(query: str) -> ColumnElement[Any]:
    lexemes = func.tsvector_to_array(func.to_tsvector(TEXT_SEARCH_CONFIG, query))
    return cast(func.array_to_string(lexemes, " | "), TSQUERY)


class ChunkRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def replace_document_chunks(self, document_id: uuid.UUID, chunks: list[Chunk]) -> int:
        await self._session.execute(delete(Chunk).where(Chunk.document_id == document_id))
        self._session.add_all(chunks)
        await self._session.flush()

        return len(chunks)

    async def search_by_vector(
        self, embedding: list[float], limit: int, section: str | None = None
    ) -> list[Chunk]:
        distance = Chunk.embedding.cosine_distance(embedding)
        stmt = select(Chunk).order_by(distance).limit(limit)

        if section is not None:
            stmt = stmt.where(Chunk.section == section)

        result = await self._session.execute(stmt)

        return list(result.scalars())

    async def search_by_text(
        self, text: str, limit: int, section: str | None = None
    ) -> list[Chunk]:
        tsquery = _any_word_tsquery(text)
        rank = func.ts_rank(Chunk.search_vector, tsquery).desc()

        stmt = (
            select(Chunk).where(Chunk.search_vector.op("@@")(tsquery)).order_by(rank).limit(limit)
        )
        if section is not None:
            stmt = stmt.where(Chunk.section == section)

        result = await self._session.execute(stmt)

        return list(result.scalars())
