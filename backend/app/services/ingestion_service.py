import asyncio
import uuid

from app.ai.chunking import TextChunk, chunk_cv
from app.ai.embeddings import Embedder
from app.models import Chunk
from app.repositories import ChunkRepository
from app.services.cv_parser import pdf_to_markdown


def _parse(pdf_bytes: bytes) -> list[TextChunk]:
    return chunk_cv(pdf_to_markdown(pdf_bytes))


class EmptyDocumentError(Exception):
    """PDF produced no chunks - parsing likely failed, e.g. a scanned image-only CV."""


class IngestionService:
    def __init__(self, repo: ChunkRepository, embedder: Embedder) -> None:
        self._repo = repo
        self._embedder = embedder

    async def ingest(self, pdf_bytes: bytes, document_id: uuid.UUID) -> int:
        text_chunks = await asyncio.to_thread(_parse, pdf_bytes)
        if not text_chunks:
            raise EmptyDocumentError(f"no chunks parsed from document {document_id}")

        vectors = await asyncio.to_thread(
            self._embedder.embed_documents,
            [chunk.content for chunk in text_chunks],
        )

        chunks = [
            Chunk(
                document_id=document_id,
                chunk_index=chunk.chunk_index,
                content=chunk.content,
                section=chunk.section,
                embedding=vector,
                embedding_model=self._embedder.model_name,
            )
            for chunk, vector in zip(text_chunks, vectors, strict=True)
        ]

        return await self._repo.replace_document_chunks(document_id, chunks)
