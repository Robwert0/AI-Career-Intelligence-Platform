import asyncio
import uuid

from app.ai.embeddings import Embedder
from app.ai.tokenizer import count_tokens, token_budget
from app.models import Chunk
from app.repositories import ChunkRepository

RANK_WINDOW_MULTIPLIER = 4


class EmptyQueryError(Exception):
    """Query has no searchable text; every chunk would be equally close to it."""


class QueryTooLongError(Exception):
    """Query exceeds the embedder's token budget, where it would be truncated in silence."""


def reciprocal_rank_fusion(rankings: list[list[Chunk]], k: int = 60, limit: int = 5) -> list[Chunk]:
    scores: dict[uuid.UUID, float] = {}
    seen: dict[uuid.UUID, Chunk] = {}

    for ranking in rankings:
        for rank, chunk in enumerate(ranking, start=1):
            scores[chunk.id] = scores.get(chunk.id, 0.0) + 1 / (k + rank)
            seen[chunk.id] = chunk

    ordered_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)

    return [seen[chunk_id] for chunk_id, _ in ordered_scores[:limit]]


class Retriever:
    def __init__(self, repo: ChunkRepository, embedder: Embedder) -> None:
        self._repo = repo
        self._embedder = embedder

    async def retrieve(self, query: str, limit: int = 5, section: str | None = None) -> list[Chunk]:
        if not query.strip():
            raise EmptyQueryError("query is empty")

        tokens = count_tokens(query)
        if tokens > token_budget():
            raise QueryTooLongError(f"query is {tokens} tokens, limit is {token_budget()}")

        window = limit * RANK_WINDOW_MULTIPLIER
        vector = await asyncio.to_thread(self._embedder.embed_query, query)
        vector_result = await self._repo.search_by_vector(vector, window, section)
        text_result = await self._repo.search_by_text(query, window, section)

        return reciprocal_rank_fusion([vector_result, text_result], limit=limit)
