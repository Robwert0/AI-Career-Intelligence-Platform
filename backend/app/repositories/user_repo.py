import uuid
from datetime import datetime
from typing import Any, cast

from sqlalchemy import func, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User


class EmailAlreadyExistsError(Exception):
    pass


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_user_by_email(self, email: str) -> User | None:
        result = await self._session.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def create_user(
        self,
        email: str,
        hashed_password: str,
        company: str | None = None,
        role: str | None = None,
    ) -> User:
        user = User(
            email=email,
            hashed_password=hashed_password,
            company=company,
            role=role,
        )
        try:
            async with self._session.begin_nested():
                self._session.add(user)
                await self._session.flush()
        except IntegrityError:
            raise EmailAlreadyExistsError() from None

        return user

    async def get_user_by_id(self, user_id: uuid.UUID) -> User | None:
        return await self._session.get(User, user_id)

    async def touch_last_active(self, user: User, at: datetime) -> None:
        user.last_active_at = at
        await self._session.flush()

    async def list_users(self, limit: int, offset: int) -> list[User]:
        result = await self._session.execute(
            select(User)
            .order_by(User.created_at.desc(), User.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars())

    async def count_users(self) -> int:
        return await self._session.scalar(select(func.count()).select_from(User)) or 0

    async def count_by_role(self) -> dict[str | None, int]:
        result = await self._session.execute(select(User.role, func.count()).group_by(User.role))
        return {role: count for role, count in result.tuples()}

    async def set_admin(self, email: str, value: bool) -> bool:
        result = cast(
            CursorResult[Any],
            await self._session.execute(
                update(User).where(User.email == email).values(is_admin=value)
            ),
        )
        return result.rowcount > 0
