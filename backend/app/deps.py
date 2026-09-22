import asyncio
import math
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.embeddings import BgeEmbedder, Embedder
from app.ai.generation import Generator
from app.ai.rag import RagPipeline, RetrieverScope
from app.ai.retriever import Retriever
from app.core.config import settings
from app.core.db import SessionLocal, get_db
from app.core.rate_limiter import Limiter, Policy, Scope
from app.models import User
from app.repositories import ChunkRepository, RefreshTokenRepository, UserRepository
from app.services import AuthService, IngestionService
from app.services.auth_service import InvalidAccessTokenError

bearer_scheme = HTTPBearer()

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def verify_trusted_origin(request: Request, origin: Annotated[str | None, Header()] = None) -> None:
    if request.method in _SAFE_METHODS:
        return

    if origin is None:
        return

    if origin == f"{request.url.scheme}://{request.url.netloc}":
        return

    if origin not in settings.cors_allowed_origins:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")


def get_user_repo(session: Annotated[AsyncSession, Depends(get_db)]) -> UserRepository:
    return UserRepository(session)


def get_refresh_token_repo(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> RefreshTokenRepository:
    return RefreshTokenRepository(session)


def get_auth_service(
    repo: Annotated[UserRepository, Depends(get_user_repo)],
    refresh_repo: Annotated[RefreshTokenRepository, Depends(get_refresh_token_repo)],
) -> AuthService:
    return AuthService(repo, refresh_repo)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> User:
    try:
        return await auth_service.authenticate(credentials.credentials)
    except InvalidAccessTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None


def get_chunk_repo(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ChunkRepository:
    return ChunkRepository(session)


def get_embedder() -> Embedder:
    return BgeEmbedder()


def get_ingestion_service(
    chunk_repo: Annotated[ChunkRepository, Depends(get_chunk_repo)],
    embedder: Annotated[Embedder, Depends(get_embedder)],
) -> IngestionService:
    return IngestionService(chunk_repo, embedder)


def get_retriever(
    chunk_repo: Annotated[ChunkRepository, Depends(get_chunk_repo)],
    embedder: Annotated[Embedder, Depends(get_embedder)],
) -> Retriever:
    return Retriever(chunk_repo, embedder)


def get_generator(request: Request) -> Generator:
    generator: Generator = request.app.state.generator
    return generator


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    return SessionLocal


def get_retriever_scope(
    session_factory: Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)],
    embedder: Annotated[Embedder, Depends(get_embedder)],
) -> RetrieverScope:
    @asynccontextmanager
    async def scope() -> AsyncIterator[Retriever]:
        async with session_factory() as session:
            yield Retriever(ChunkRepository(session), embedder)

    return scope


def get_generation_slots(request: Request) -> asyncio.Semaphore:
    slots: asyncio.Semaphore = request.app.state.generation_slots
    return slots


def get_rag_pipeline(
    retriever_scope: Annotated[RetrieverScope, Depends(get_retriever_scope)],
    generator: Annotated[Generator, Depends(get_generator)],
    slots: Annotated[asyncio.Semaphore, Depends(get_generation_slots)],
) -> RagPipeline:
    return RagPipeline(retriever_scope, generator, slots)


def get_limiter(request: Request) -> Limiter:
    limiter: Limiter = request.app.state.limiter
    return limiter


def _client_ip(request: Request) -> str:
    if request.client is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Service unavailable")
    return request.client.host


async def _enforce(policy: Policy, identity: str, limiter: Limiter) -> None:
    try:
        decision = await limiter.check(policy, identity, now=time.time())
    except RedisError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Service unavailable") from None
    if not decision.allowed:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many requests",
            headers={"Retry-After": str(math.ceil(decision.retry_after_seconds))},
        )


def rate_limit(policy: Policy) -> Callable[..., Awaitable[None]]:
    # Two closures, not one: FastAPI resolves dependencies from the signature, so an IP-scoped
    # policy must not carry the auth dependency or /auth/login would require a login.
    async def by_ip(request: Request, limiter: Annotated[Limiter, Depends(get_limiter)]) -> None:
        await _enforce(policy, _client_ip(request), limiter)

    async def by_user(
        user: Annotated[User, Depends(get_current_user)],
        limiter: Annotated[Limiter, Depends(get_limiter)],
    ) -> None:
        await _enforce(policy, str(user.id), limiter)

    return by_ip if policy.scope is Scope.IP else by_user
