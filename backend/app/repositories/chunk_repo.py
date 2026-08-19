import uuid

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Chunk


class ChunkRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def replace_document_chunks(self, document_id: uuid.UUID, chunks: list[Chunk]) -> int:
        await self._session.execute(delete(Chunk).where(Chunk.document_id == document_id))
        self._session.add_all(chunks)
        await self._session.flush()

        return len(chunks)
