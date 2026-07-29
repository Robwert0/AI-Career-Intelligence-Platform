import asyncio
import secrets
from uuid import UUID

import jwt

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models import User
from app.repositories.user_repo import EmailAlreadyExistsError, UserRepository
from app.schemas import UserCreate

_DUMMY_HASH = hash_password(secrets.token_urlsafe(32))


class EmailAlreadyRegisteredError(Exception):
    pass


class InvalidCredentialsError(Exception):
    """Invalid credentials error"""


class InvalidAccessTokenError(Exception):
    """Token verified but does not identify a usable account."""


class AuthService:
    def __init__(self, repo: UserRepository) -> None:
        self._repo = repo

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
            create_refresh_token(str(user.id)),
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
