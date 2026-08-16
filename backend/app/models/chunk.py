import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    Computed,
    DateTime,
    Index,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
)

from app.core.db import Base

SECTIONS = ("experience", "projects", "skills")


class Chunk(Base):
    __tablename__ = "chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_chunks_document_id_chunk_index"),
        CheckConstraint(
            "section IN ({})".format(", ".join(f"'{section}'" for section in SECTIONS)),
            name="ck_chunks_section",
        ),
        # A failed embedding call returns all zeros, which inserts cleanly and then makes every
        # cosine distance NaN — Postgres sorts NaN last, so the chunk is silently unretrievable.
        # vector_norm, not l2_norm: the latter is overloaded across vector/halfvec/sparsevec and
        # Postgres cannot resolve it inside a CHECK.
        CheckConstraint("vector_norm(embedding) > 0", name="ck_chunks_embedding_nonzero"),
        Index(
            "ix_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("ix_chunks_search_vector", "search_vector", postgresql_using="gin"),
        Index("ix_chunks_section", "section"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(index=True)
    chunk_index: Mapped[int]
    content: Mapped[str]
    section: Mapped[str]
    embedding: Mapped[list[float]] = mapped_column(Vector(384))
    embedding_model: Mapped[str]
    search_vector: Mapped[str] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('english', content)", persisted=True),
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
