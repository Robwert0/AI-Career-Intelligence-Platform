import asyncio
import uuid

from app.ai.embeddings import Embedder, QueryTooLongError
from app.models import Chunk
from app.repositories import ChunkRepository

RANK_WINDOW_MULTIPLIER = 4
MAX_QUERY_CHARS = 8000
MAX_LIMIT = 100


class EmptyQueryError(Exception):
    """Query has no searchable text; every chunk would be equally close to it."""


def reciprocal_rank_fusion(rankings: list[list[Chunk]], k: int = 60, limit: int = 5) -> list[Chunk]:
    if k < 1:
        raise ValueError(f"k must be at least 1, got {k}")
    if limit < 1:
        raise ValueError(f"limit must be at least 1, got {limit}")

    scores: dict[uuid.UUID, float] = {}
    seen: dict[uuid.UUID, Chunk] = {}

    for ranking in rankings:
        for rank, chunk in enumerate(ranking, start=1):
            if chunk.id is None:
                raise ValueError("cannot fuse a chunk that has not been persisted")
            scores[chunk.id] = scores.get(chunk.id, 0.0) + 1 / (k + rank)
            seen[chunk.id] = chunk

    ordered_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)

    return [seen[chunk_id] for chunk_id, _ in ordered_scores[:limit]]


class Retriever:
    def __init__(self, repo: ChunkRepository, embedder: Embedder) -> None:
        self._repo = repo
        self._embedder = embedder

    async def retrieve(
        self,
        query: str,
        *,
        document_id: uuid.UUID | None,
        limit: int = 5,
        section: str | None = None,
    ) -> list[Chunk]:
        if not 1 <= limit <= MAX_LIMIT:
            raise ValueError(f"limit must be between 1 and {MAX_LIMIT}, got {limit}")
        if not query.strip():
            raise EmptyQueryError("query is empty")
        if len(query) > MAX_QUERY_CHARS:
            raise QueryTooLongError(f"query is {len(query)} characters, limit is {MAX_QUERY_CHARS}")

        window = limit * RANK_WINDOW_MULTIPLIER
        vector = await asyncio.to_thread(self._embedder.embed_query, query)
        vector_result = await self._repo.search_by_vector(vector, window, section, document_id)
        text_result = await self._repo.search_by_text(query, window, section, document_id)

        return reciprocal_rank_fusion([vector_result, text_result], limit=limit)
