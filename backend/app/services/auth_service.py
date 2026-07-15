import asyncio

from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
)
from app.models import User
from app.repositories.user_repo import UserRepository
from app.schemas import UserCreate


class EmailAlreadyRegisteredError(Exception):
    pass


class InvalidCredentialsError(Exception):
    """Invalid credentials error"""


class AuthService:
    def __init__(self, repo: UserRepository) -> None:
        self._repo = repo

    async def register(self, data: UserCreate) -> User:
        if await self._repo.get_user_by_email(data.email) is not None:
            raise EmailAlreadyRegisteredError
        hashed = await asyncio.to_thread(hash_password, data.password)
        return await self._repo.create_user(email=data.email, hashed_password=hashed)

    async def login(self, email: str, password: str) -> tuple[str, str]:
        user = await self._repo.get_user_by_email(email)
        if user is None:
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
