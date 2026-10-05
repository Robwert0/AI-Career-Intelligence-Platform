import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta

import httpx
import pytest_asyncio
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.policies import ADMIN_IP, ADMIN_USER
from app.core.redis import create_redis
from app.core.retention_marker import RetentionMarker
from app.core.security import create_access_token
from app.deps import get_retention_marker
from app.main import app
from app.models import User

T0 = datetime(2026, 10, 1, tzinfo=UTC)


@pytest_asyncio.fixture(autouse=True)
async def marker() -> AsyncGenerator[RetentionMarker]:
    # The client fixture skips the lifespan, so app.state.redis does not exist in these tests.
    redis: Redis = create_redis()
    key = f"test:{uuid.uuid4()}"
    marker = RetentionMarker(redis, key=key)
    app.dependency_overrides[get_retention_marker] = lambda: marker
    yield marker
    await redis.delete(key)
    await redis.aclose()


async def _user(
    db_session: AsyncSession,
    email: str,
    *,
    is_admin: bool = False,
    role: str | None = None,
    company: str | None = None,
    minutes: int = 0,
) -> User:
    user = User(
        email=email,
        hashed_password="x",
        is_admin=is_admin,
        role=role,
        company=company,
        created_at=T0 + timedelta(minutes=minutes),
    )
    db_session.add(user)
    await db_session.flush()
    return user


def _auth(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(str(user.id))}"}


async def test_anonymous_gets_401(client: httpx.AsyncClient) -> None:
    assert (await client.get("/admin/users")).status_code == 401


async def test_a_non_admin_gets_404(client: httpx.AsyncClient, db_session: AsyncSession) -> None:
    jane = await _user(db_session, "jane@acme.dev")

    response = await client.get("/admin/users", headers=_auth(jane))

    assert response.status_code == 404


async def test_admin_sees_users_newest_first_with_totals(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    admin = await _user(db_session, "robert@test.dev", is_admin=True, minutes=0)
    await _user(db_session, "jane@acme.dev", role="recruiter", company="Acme", minutes=1)
    await _user(db_session, "sam@beta.dev", role="engineer", minutes=2)

    response = await client.get("/admin/users", headers=_auth(admin))

    assert response.status_code == 200
    body = response.json()
    assert [row["email"] for row in body["items"]] == [
        "sam@beta.dev",
        "jane@acme.dev",
        "robert@test.dev",
    ]
    assert body["items"][1]["company"] == "Acme"
    assert body["items"][0]["last_active_at"] is None
    assert "hashed_password" not in body["items"][0]
    assert "is_admin" not in body["items"][0]
    assert body["total"] == 3
    assert body["by_role"] == {
        "recruiter": 1,
        "hiring_manager": 0,
        "engineer": 1,
        "other": 0,
        "unspecified": 1,
    }


async def test_the_user_list_is_not_cached(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    admin = await _user(db_session, "robert@test.dev", is_admin=True)

    response = await client.get("/admin/users", headers=_auth(admin))

    assert response.headers["cache-control"] == "no-store"


async def test_paging_slices_items_but_not_totals(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    admin = await _user(db_session, "robert@test.dev", is_admin=True, minutes=0)
    for i in range(1, 4):
        await _user(db_session, f"u{i}@test.dev", minutes=i)

    response = await client.get("/admin/users?limit=2&offset=1", headers=_auth(admin))

    body = response.json()
    assert [row["email"] for row in body["items"]] == ["u2@test.dev", "u1@test.dev"]
    assert body["total"] == 4
    assert (body["limit"], body["offset"]) == (2, 1)


async def test_paging_bounds_are_validated(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    admin = await _user(db_session, "robert@test.dev", is_admin=True)

    for query in ("limit=0", "limit=101", "offset=-1"):
        response = await client.get(f"/admin/users?{query}", headers=_auth(admin))
        assert response.status_code == 422, query


async def test_revoking_admin_takes_effect_on_the_next_request(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    admin = await _user(db_session, "robert@test.dev", is_admin=True)
    headers = _auth(admin)
    assert (await client.get("/admin/users", headers=headers)).status_code == 200

    admin.is_admin = False
    await db_session.flush()

    assert (await client.get("/admin/users", headers=headers)).status_code == 404


async def test_me_exposes_the_admin_flag(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    admin = await _user(db_session, "robert@test.dev", is_admin=True)

    response = await client.get("/users/me", headers=_auth(admin))

    assert response.json()["is_admin"] is True


async def test_a_rate_limited_non_admin_still_gets_404(
    limited_client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    jane = await _user(db_session, "jane@acme.dev")
    attempts = ADMIN_USER.capacity + 1
    assert attempts <= ADMIN_IP.capacity

    statuses = [
        (await limited_client.get("/admin/users", headers=_auth(jane))).status_code
        for _ in range(attempts)
    ]

    assert statuses == [404] * attempts


async def test_the_last_purge_time_is_reported(
    client: httpx.AsyncClient, db_session: AsyncSession, marker: RetentionMarker
) -> None:
    admin = await _user(db_session, "robert@test.dev", is_admin=True)
    await marker.record(T0)

    response = await client.get("/admin/users", headers=_auth(admin))

    assert datetime.fromisoformat(response.json()["last_purge_at"]) == T0


async def test_no_purge_yet_is_reported_as_null(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    admin = await _user(db_session, "robert@test.dev", is_admin=True)

    response = await client.get("/admin/users", headers=_auth(admin))

    assert response.status_code == 200
    assert response.json()["last_purge_at"] is None


async def test_an_unreachable_marker_still_serves_the_page(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    admin = await _user(db_session, "robert@test.dev", is_admin=True)
    dead = Redis.from_url("redis://127.0.0.1:1/0", socket_connect_timeout=0.5)
    app.dependency_overrides[get_retention_marker] = lambda: RetentionMarker(dead)
    try:
        response = await client.get("/admin/users", headers=_auth(admin))
    finally:
        await dead.aclose()

    assert response.status_code == 200
    assert response.json()["last_purge_at"] is None
