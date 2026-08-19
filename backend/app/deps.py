from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings import BgeEmbedder, Embedder
from app.ai.retriever import Retriever
from app.core.config import settings
from app.core.db import get_db
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
