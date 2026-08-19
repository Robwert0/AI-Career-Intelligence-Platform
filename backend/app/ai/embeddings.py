import functools
from typing import Protocol

from sentence_transformers import SentenceTransformer

from app.ai.tokenizer import count_tokens, token_budget
from app.core.config import settings

BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


class QueryTooLongError(Exception):
    """Query does not fit the model's input window and would be truncated in silence."""


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
    def __init__(self) -> None:
        self.model = get_model()
        dimensions = self.model.get_embedding_dimension()
        if dimensions is None or dimensions != settings.embedding_dim:
            raise ValueError(
                f"{self.model_name} reports {dimensions} dimensions, not the configured "
                f"{settings.embedding_dim}; every insert into chunks.embedding would be rejected"
            )
        self._dimensions = dimensions

    @property
    def model_name(self) -> str:
        return f"{settings.embedding_model}@{settings.embedding_model_revision}"

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = self.model.encode(texts, normalize_embeddings=True).tolist()
        return vectors

    def embed_query(self, text: str) -> list[float]:
        tokens = count_tokens(BGE_QUERY_PREFIX + text)
        if tokens > token_budget():
            raise QueryTooLongError(
                f"query is {tokens} tokens with the retrieval prefix, limit is {token_budget()}"
            )
        vector: list[float] = self.model.encode(
            inputs=text, prompt=BGE_QUERY_PREFIX, normalize_embeddings=True
        ).tolist()
        return vector
