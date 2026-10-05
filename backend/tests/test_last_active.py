from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories import UserRepository

EMAIL = "active@test.dev"
PASSWORD = "supersecret1"


async def _stored_last_active(db_session: AsyncSession) -> datetime | None:
    user = await UserRepository(db_session).get_user_by_email(EMAIL)
    assert user is not None
    await db_session.refresh(user)
    return user.last_active_at


async def test_register_alone_does_not_mark_activity(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    await client.post("/auth/register", json={"email": EMAIL, "password": PASSWORD})

    assert await _stored_last_active(db_session) is None


async def test_login_marks_activity(client: httpx.AsyncClient, db_session: AsyncSession) -> None:
    await client.post("/auth/register", json={"email": EMAIL, "password": PASSWORD})
    before = datetime.now(UTC)

    await client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})

    stamped = await _stored_last_active(db_session)
    assert stamped is not None and stamped >= before - timedelta(seconds=1)


async def test_refresh_moves_activity_forward(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    await client.post("/auth/register", json={"email": EMAIL, "password": PASSWORD})
    await client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})
    after_login = await _stored_last_active(db_session)

    response = await client.post("/auth/refresh")

    assert response.status_code == 200
    after_refresh = await _stored_last_active(db_session)
    assert after_login is not None and after_refresh is not None
    assert after_refresh > after_login


async def test_a_failed_login_does_not_mark_activity(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    await client.post("/auth/register", json={"email": EMAIL, "password": PASSWORD})

    await client.post("/auth/login", json={"email": EMAIL, "password": "wrongpassword"})

    assert await _stored_last_active(db_session) is None
