import functools
from typing import Protocol

from sentence_transformers import SentenceTransformer

from app.core.config import settings

BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


class Embedder(Protocol):
    @property
    def model_name(self) -> str: ...

    @property
    def dimensions(self) -> int: ...

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


@functools.lru_cache
def get_model() -> SentenceTransformer:
    return SentenceTransformer(settings.embedding_model, revision=settings.embedding_model_revision)


class BgeEmbedder:
    def __init__(self, model: SentenceTransformer | None = None) -> None:
        self.model = get_model() if model is None else model

    @property
    def model_name(self) -> str:
        return settings.embedding_model

    @property
    def dimensions(self) -> int:
        return settings.embedding_dim

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = self.model.encode(texts).tolist()
        return vectors

    def embed_query(self, text: str) -> list[float]:
        vectors: list[float] = self.model.encode(inputs=text, prompt=BGE_QUERY_PREFIX).tolist()
        return vectors
