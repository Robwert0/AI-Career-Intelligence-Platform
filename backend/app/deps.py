from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import get_db
from app.models import User
from app.repositories import RefreshTokenRepository, UserRepository
from app.services import AuthService
from app.services.auth_service import InvalidAccessTokenError

bearer_scheme = HTTPBearer()


def verify_trusted_origin(request: Request, origin: Annotated[str | None, Header()] = None) -> None:
    # An absent Origin passes: modern browsers send it on every cross-site POST, so its absence
    # cannot be forged from one, and rejecting it would break every non-browser client.
    if origin is None:
        return
    # The CORS allowlist deliberately excludes this API's own origin, but same-origin POSTs
    # (Swagger at /docs) still carry an Origin header and must not be rejected as cross-site.
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
