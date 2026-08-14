import asyncio
import secrets
from datetime import UTC, datetime, timedelta
from typing import NoReturn
from uuid import UUID, uuid4

import jwt

from app.core.config import settings
from app.core.security import (
    create_access_token,
    decode_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.models import User
from app.repositories.refresh_token_repo import RefreshTokenRepository
from app.repositories.user_repo import EmailAlreadyExistsError, UserRepository
from app.schemas import UserCreate

_DUMMY_HASH = hash_password(secrets.token_urlsafe(32))


class EmailAlreadyRegisteredError(Exception):
    pass


class InvalidCredentialsError(Exception):
    """Invalid credentials error"""


class InvalidAccessTokenError(Exception):
    """Token verified but does not identify a usable account."""


class InvalidRefreshTokenError(Exception):
    """Refresh token missing, unknown, expired, revoked, or already spent."""


class AuthService:
    def __init__(self, repo: UserRepository, refresh_repo: RefreshTokenRepository) -> None:
        self._repo = repo
        self._refresh_repo = refresh_repo

    async def _issue_refresh_token(self, user_id: UUID, family_id: UUID) -> str:
        raw_token = generate_refresh_token()
        await self._refresh_repo.create(
            user_id=user_id,
            family_id=family_id,
            token_hash=hash_refresh_token(raw_token),
            expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days),
        )
        return raw_token

    async def register(self, data: UserCreate) -> User:
        if await self._repo.get_user_by_email(data.email) is not None:
            raise EmailAlreadyRegisteredError
        hashed = await asyncio.to_thread(hash_password, data.password)
        try:
            user = await self._repo.create_user(
                email=data.email,
                hashed_password=hashed,
            )
        except EmailAlreadyExistsError:
            raise EmailAlreadyRegisteredError from None
        return user

    async def login(self, email: str, password: str) -> tuple[str, str]:
        user = await self._repo.get_user_by_email(email)
        if user is None:
            await asyncio.to_thread(
                verify_password,
                plain_password=password,
                hashed_password=_DUMMY_HASH,
            )
            raise InvalidCredentialsError

        if not await asyncio.to_thread(
            verify_password,
            plain_password=password,
            hashed_password=user.hashed_password,
        ):
            raise InvalidCredentialsError

        return (
            create_access_token(str(user.id)),
            await self._issue_refresh_token(user.id, family_id=uuid4()),
        )

    async def _reject_unusable_token(self, token_hash: str) -> NoReturn:
        token = await self._refresh_repo.get_by_hash(token_hash)
        # Spent but not revoked is a replay: whoever holds this is not who rotated it.
        # Checked before expiry, so a token that is both spent and expired is still theft.
        if token is not None and token.revoked_at is None and token.used_at is not None:
            await self._refresh_repo.revoke_family(token.family_id)
        raise InvalidRefreshTokenError

    async def refresh(self, raw_token: str) -> tuple[str, str]:
        token_hash = hash_refresh_token(raw_token)
        spent = await self._refresh_repo.consume(token_hash)
        if spent is None:
            await self._reject_unusable_token(token_hash)

        user = await self._repo.get_user_by_id(spent.user_id)
        if user is None:
            raise InvalidRefreshTokenError

        return (
            create_access_token(str(user.id)),
            await self._issue_refresh_token(user.id, family_id=spent.family_id),
        )

    async def authenticate(self, token: str) -> User:
        try:
            payload = decode_token(token, expected_type="access")
            user_id = UUID(payload["sub"])
        except jwt.InvalidTokenError, ValueError, TypeError, AttributeError:
            raise InvalidAccessTokenError from None

        user = await self._repo.get_user_by_id(user_id)
        if user is None:
            raise InvalidAccessTokenError

        return user
