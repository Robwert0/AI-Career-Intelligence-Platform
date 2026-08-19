import uuid
from collections.abc import AsyncGenerator
from typing import Annotated

import httpx
import pytest
from fakes import FakeEmbedder
from fastapi import Depends, FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings import Embedder
from app.ai.retriever import Retriever
from app.core.config import settings
from app.core.db import get_db
from app.deps import get_embedder, get_retriever
from app.models import Chunk
from app.repositories import ChunkRepository

DOCUMENT_ID = uuid.UUID("44444444-4444-4444-4444-444444444444")


def build_app() -> FastAPI:
    api = FastAPI()

    @api.get("/probe/embedder")
    async def probe_embedder(
        embedder: Annotated[Embedder, Depends(get_embedder)],
    ) -> dict[str, str]:
        return {"model": embedder.model_name}

    @api.get("/probe/retrieve")
    async def probe_retrieve(
        retriever: Annotated[Retriever, Depends(get_retriever)],
    ) -> dict[str, int]:
        return {"hits": len(await retriever.retrieve("kubernetes", limit=2))}

    return api


@pytest.fixture
async def wired(db_session: AsyncSession) -> AsyncGenerator[httpx.AsyncClient]:
    embedder = FakeEmbedder()
    content = "Kubernetes, Terraform, PostgreSQL and Redis."
    await ChunkRepository(db_session).replace_document_chunks(
        DOCUMENT_ID,
        [
            Chunk(
                document_id=DOCUMENT_ID,
                chunk_index=0,
                content=content,
                section="skills",
                embedding=embedder.embed_documents([content])[0],
                embedding_model=embedder.model_name,
            )
        ],
    )

    async def override_get_db() -> AsyncGenerator[AsyncSession]:
        yield db_session

    api = build_app()
    api.dependency_overrides[get_db] = override_get_db
    api.dependency_overrides[get_embedder] = lambda: embedder
    transport = httpx.ASGITransport(app=api)
    async with httpx.AsyncClient(transport=transport, base_url="https://test") as client:
        yield client


async def test_the_retriever_chain_resolves_through_fastapi(wired: httpx.AsyncClient) -> None:
    response = await wired.get("/probe/retrieve")
    assert response.status_code == 200
    assert response.json() == {"hits": 1}


async def test_overriding_get_embedder_swaps_the_implementation(wired: httpx.AsyncClient) -> None:
    response = await wired.get("/probe/embedder")
    assert response.json() == {"model": FakeEmbedder().model_name}


async def test_without_an_override_the_real_embedder_is_constructed(
    db_session: AsyncSession,
) -> None:
    async def override_get_db() -> AsyncGenerator[AsyncSession]:
        yield db_session

    api = build_app()
    api.dependency_overrides[get_db] = override_get_db
    transport = httpx.ASGITransport(app=api)
    async with httpx.AsyncClient(transport=transport, base_url="https://test") as client:
        response = await client.get("/probe/embedder")

    expected = f"{settings.embedding_model}@{settings.embedding_model_revision}"
    assert response.json() == {"model": expected}
