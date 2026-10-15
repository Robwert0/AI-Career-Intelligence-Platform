import uuid
from typing import Any, cast

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Chunk
from app.repositories import ChunkRepository


class _Rows:
    def __init__(self, rows: list[tuple[Chunk, float]]) -> None:
        self._rows = rows

    def all(self) -> list[tuple[Chunk, float]]:
        return self._rows


class _ScrambledSession:
    # Mimics relaxed_order: a filtered HNSW scan may hand rows back slightly out of order
    def __init__(self, rows: list[tuple[Chunk, float]]) -> None:
        self._rows = rows

    async def execute(self, statement: Any) -> _Rows:
        return _Rows(self._rows)


async def test_vector_hits_come_back_nearest_first_even_when_the_scan_does_not() -> None:
    scrambled = [(Chunk(content=f"distance {d}"), d) for d in (0.30, 0.10, 0.40, 0.20)]
    repo = ChunkRepository(cast(AsyncSession, _ScrambledSession(scrambled)))

    hits = await repo.search_by_vector([0.0], limit=4, document_id=uuid.uuid4())

    assert [distance for _, distance in hits] == [0.10, 0.20, 0.30, 0.40]
    assert [chunk.content for chunk, _ in hits] == [f"distance {d}" for d in (0.1, 0.2, 0.3, 0.4)]
