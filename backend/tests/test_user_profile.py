import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User


async def test_new_columns_default_to_empty_and_non_admin(db_session: AsyncSession) -> None:
    user = User(email="a@test.dev", hashed_password="x")
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)

    assert user.company is None
    assert user.role is None
    assert user.is_admin is False
    assert user.last_active_at is None


async def test_the_database_rejects_an_unknown_role(db_session: AsyncSession) -> None:
    db_session.add(User(email="b@test.dev", hashed_password="x", role="ceo"))

    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            await db_session.flush()
