import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import RefreshToken, User


async def make_user(db_session: AsyncSession) -> User:
    user = User(email=f"{uuid.uuid4()}@test.dev", hashed_password="not-a-real-hash")
    db_session.add(user)
    await db_session.flush()
    return user


def in_days(days: int) -> datetime:
    return datetime.now(UTC) + timedelta(days=days)


async def test_a_new_row_is_unused_and_unrevoked(db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    token = RefreshToken(
        user_id=user.id,
        family_id=uuid.uuid4(),
        token_hash="a" * 64,
        expires_at=in_days(7),
    )
    db_session.add(token)
    await db_session.flush()

    assert token.id is not None
    assert token.used_at is None
    assert token.revoked_at is None
    assert token.created_at is not None


async def test_token_hash_is_unique(db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    for _ in range(2):
        db_session.add(
            RefreshToken(
                user_id=user.id,
                family_id=uuid.uuid4(),
                token_hash="b" * 64,
                expires_at=in_days(7),
            )
        )

    with pytest.raises(IntegrityError):
        await db_session.flush()
