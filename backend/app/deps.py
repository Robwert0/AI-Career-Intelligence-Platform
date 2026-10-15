import asyncio
import logging
import math
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from functools import partial
from typing import Annotated

from fastapi import Cookie, Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.embeddings import BgeEmbedder, Embedder
from app.ai.generation import Generator
from app.ai.rag import RagPipeline, RetrieverScope
from app.ai.retriever import Retriever
from app.core import policies
from app.core.analysis_registry import AnalysisRegistry
from app.core.config import settings
from app.core.db import SessionLocal, get_db
from app.core.job_store import JobStore
from app.core.rate_limiter import (
    Decision,
    Limiter,
    Policy,
    Scope,
    ip_identity,
    ip_prefix_identity,
)
from app.core.retention_marker import RetentionMarker
from app.core.security import LOGIN_DEVICE_COOKIE, login_device_id
from app.models import User
from app.repositories import ChunkRepository, RefreshTokenRepository, UserRepository
from app.schemas import LoginRequest
from app.services import AuthService, IngestionService
from app.services.admin_service import AdminService
from app.services.auth_service import InvalidAccessTokenError, LoginAccount
from app.services.match_service import MatchService
from app.workers.queue import TaskQueue

logger = logging.getLogger(__name__)

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


async def get_current_admin(user: Annotated[User, Depends(get_current_user)]) -> User:
    # 404, not 403: don't confirm to a signed-in non-admin that they lack the flag.
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")
    return user


def get_retention_marker(request: Request) -> RetentionMarker:
    return RetentionMarker(request.app.state.redis)


def get_admin_service(
    repo: Annotated[UserRepository, Depends(get_user_repo)],
    marker: Annotated[RetentionMarker, Depends(get_retention_marker)],
) -> AdminService:
    return AdminService(repo, marker)


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


def get_global_identity() -> str:
    return "all"


def _client_host(request: Request) -> str:
    if request.client is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Service unavailable")
    return request.client.host


def _too_many_requests(decision: Decision) -> HTTPException:
    return HTTPException(
        status.HTTP_429_TOO_MANY_REQUESTS,
        "Too many requests",
        headers={"Retry-After": str(math.ceil(decision.retry_after_seconds))},
    )


async def _decide(
    decide: Callable[[Policy, str], Awaitable[Decision]], policy: Policy, identity: str
) -> Decision:
    try:
        return await decide(policy, identity)
    except RedisError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Service unavailable") from None


def _log_refusal(policy: Policy, decision: Decision) -> None:
    # Per-IP and per-user refusals are routine and would name a client. A global ceiling or a
    # sign-in lockout is a signal worth a warning, logged by policy name only, never its key.
    match policy.scope:
        case Scope.GLOBAL:
            event = "rate limit ceiling reached, refusing requests"
        case Scope.ACCOUNT:
            event = "sign-in failure limit reached, refusing sign-ins"
        case _:
            return
    if decision.first_refusal:
        logger.warning(
            "%s policy=%s scope=%s retry_after_s=%d",
            event,
            policy.name,
            policy.scope,
            math.ceil(decision.retry_after_seconds),
        )
    else:
        logger.debug("%s policy=%s scope=%s", event, policy.name, policy.scope)


async def enforce_rate_limit(policy: Policy, identity: str, limiter: Limiter) -> None:
    # Takes a token; the reserving context managers below build on this so they cannot drift.
    decision = await _decide(partial(limiter.check, now=time.time()), policy, identity)
    if not decision.allowed:
        _log_refusal(policy, decision)
        raise _too_many_requests(decision)


@asynccontextmanager
async def reserved_rate_limit(
    policy: Policy, identity: str, limiter: Limiter
) -> AsyncIterator[None]:
    # The atomic take before the work is what holds the cap under a concurrent burst; checking
    # first and spending after lets the whole burst through.
    await enforce_rate_limit(policy, identity, limiter)
    try:
        yield
    except BaseException:
        await _refund(policy, identity, limiter)
        raise


@asynccontextmanager
async def failure_rate_limit(
    policy: Policy, identity: str, limiter: Limiter
) -> AsyncIterator[None]:
    # The inverse of reserved_rate_limit: taken up front for the same burst-safety, refunded only
    # when the block completes, so only failed attempts stay spent.
    await enforce_rate_limit(policy, identity, limiter)
    yield
    await _refund(policy, identity, limiter)


def _login_bucket(account_key: str, device_token: str | None) -> tuple[Policy, str]:
    # A browser that has signed in to this account before gets its own failure budget, so an
    # attacker draining the account's shared one cannot lock the owner out of a known device.
    device_id = None if device_token is None else login_device_id(device_token, account_key)
    if device_id is None:
        return policies.LOGIN_ACCOUNT, account_key
    return policies.LOGIN_DEVICE, device_id


async def login_failure_limit(
    data: LoginRequest,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
    limiter: Annotated[Limiter, Depends(get_limiter)],
    device_token: Annotated[str | None, Cookie(alias=LOGIN_DEVICE_COOKIE)] = None,
) -> AsyncIterator[LoginAccount]:
    # The account is resolved before the take so every spelling CITEXT matches to one row spends
    # one bucket; the lookup runs for unknown emails too, so the limit leaks no existence. FastAPI
    # throws the handler's 401 in at the yield, which skips the refund: only failures stay spent.
    account = await auth_service.resolve_login(data.email)
    policy, identity = _login_bucket(account.key, device_token)
    async with failure_rate_limit(policy, identity, limiter):
        yield account


async def _refund(policy: Policy, identity: str, limiter: Limiter) -> None:
    # Swallowed so the caller's original error surfaces; a lost token is the safe direction.
    try:
        await limiter.refund(policy, identity, now=time.time())
    except RedisError:
        logger.exception("rate limit refund failed, token stays spent policy=%s", policy.name)


def rate_limit(policy: Policy) -> Callable[..., Awaitable[None]]:
    # One closure per scope: FastAPI resolves dependencies from the signature, so an IP-scoped
    # policy must not carry the auth dependency or /auth/login would require a login.
    async def by_ip(request: Request, limiter: Annotated[Limiter, Depends(get_limiter)]) -> None:
        await enforce_rate_limit(policy, ip_identity(_client_host(request)), limiter)

    async def by_ip_prefix(
        request: Request, limiter: Annotated[Limiter, Depends(get_limiter)]
    ) -> None:
        await enforce_rate_limit(policy, ip_prefix_identity(_client_host(request)), limiter)

    async def by_user(
        user: Annotated[User, Depends(get_current_user)],
        limiter: Annotated[Limiter, Depends(get_limiter)],
    ) -> None:
        await enforce_rate_limit(policy, str(user.id), limiter)

    async def by_global(
        identity: Annotated[str, Depends(get_global_identity)],
        limiter: Annotated[Limiter, Depends(get_limiter)],
    ) -> None:
        await enforce_rate_limit(policy, identity, limiter)

    match policy.scope:
        case Scope.IP:
            return by_ip
        case Scope.IP_PREFIX:
            return by_ip_prefix
        case Scope.USER:
            return by_user
        case Scope.GLOBAL:
            return by_global
    raise ValueError(f"unhandled scope {policy.scope}")


def get_job_store(request: Request) -> JobStore:
    return JobStore(request.app.state.redis, ttl_seconds=settings.job_ttl_seconds)


def get_task_queue(request: Request) -> TaskQueue:
    queue: TaskQueue = request.app.state.task_queue
    return queue


def get_analysis_registry(request: Request) -> AnalysisRegistry:
    return AnalysisRegistry(request.app.state.redis, ttl_seconds=settings.job_ttl_seconds)


def get_match_service(
    store: Annotated[JobStore, Depends(get_job_store)],
    queue: Annotated[TaskQueue, Depends(get_task_queue)],
    registry: Annotated[AnalysisRegistry, Depends(get_analysis_registry)],
) -> MatchService:
    return MatchService(store, queue, registry)
