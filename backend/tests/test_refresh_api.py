from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_refresh_token
from app.models import RefreshToken, User

EMAIL = "robert@test.dev"
PASSWORD = "supersecret1"


async def register(client: httpx.AsyncClient) -> httpx.Response:
    return await client.post("/auth/register", json={"email": EMAIL, "password": PASSWORD})


async def login(client: httpx.AsyncClient) -> httpx.Response:
    return await client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})


async def all_tokens(db_session: AsyncSession) -> list[RefreshToken]:
    db_session.expire_all()
    result = await db_session.execute(select(RefreshToken))
    return list(result.scalars().all())


def presenting(raw: str) -> dict[str, str]:
    return {"cookie": f"__Host-refresh_token={raw}"}


def in_the_past() -> datetime:
    return datetime.now(UTC) - timedelta(days=1)


async def test_login_persists_exactly_one_token(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    await register(client)
    await login(client)

    assert len(await all_tokens(db_session)) == 1


async def test_login_cookie_is_opaque_not_a_jwt(client: httpx.AsyncClient) -> None:
    await register(client)
    raw = (await login(client)).cookies["__Host-refresh_token"]

    assert "." not in raw
    assert len(raw) >= 43


async def test_only_the_hash_of_the_token_is_stored(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    await register(client)
    raw = (await login(client)).cookies["__Host-refresh_token"]

    token = (await all_tokens(db_session))[0]
    assert token.token_hash == hash_refresh_token(raw)
    assert raw not in token.token_hash


async def test_two_logins_are_two_families(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    await register(client)
    await login(client)
    await login(client)

    tokens = await all_tokens(db_session)
    assert len({token.family_id for token in tokens}) == 2


async def test_refresh_rotates_the_token(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    await register(client)
    old_raw = (await login(client)).cookies["__Host-refresh_token"]

    response = await client.post("/auth/refresh")

    assert response.status_code == 200
    new_raw = response.cookies["__Host-refresh_token"]
    assert new_raw != old_raw
    assert response.json()["access_token"]
    assert response.json()["token_type"] == "bearer"

    tokens = await all_tokens(db_session)
    assert len(tokens) == 2
    parent = next(t for t in tokens if t.token_hash == hash_refresh_token(old_raw))
    child = next(t for t in tokens if t.token_hash == hash_refresh_token(new_raw))
    assert parent.used_at is not None
    assert child.used_at is None
    assert child.family_id == parent.family_id
    assert child.expires_at >= parent.expires_at


async def test_the_rotated_token_authenticates(client: httpx.AsyncClient) -> None:
    await register(client)
    await login(client)
    access_token = (await client.post("/auth/refresh")).json()["access_token"]

    response = await client.get("/users/me", headers={"Authorization": f"Bearer {access_token}"})

    assert response.status_code == 200
    assert response.json()["email"] == EMAIL


async def test_the_child_token_can_itself_be_refreshed(client: httpx.AsyncClient) -> None:
    await register(client)
    await login(client)

    assert (await client.post("/auth/refresh")).status_code == 200
    assert (await client.post("/auth/refresh")).status_code == 200


async def test_a_replayed_token_kills_the_whole_family(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    await register(client)
    old_raw = (await login(client)).cookies["__Host-refresh_token"]
    child_raw = (await client.post("/auth/refresh")).cookies["__Host-refresh_token"]

    replay = await client.post("/auth/refresh", headers=presenting(old_raw))

    assert replay.status_code == 401
    tokens = await all_tokens(db_session)
    assert len(tokens) == 2
    assert all(t.revoked_at is not None for t in tokens)

    reused_child = await client.post("/auth/refresh", headers=presenting(child_raw))
    assert reused_child.status_code == 401


async def test_an_expired_token_leaves_the_family_intact(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    await register(client)
    await login(client)
    token = (await all_tokens(db_session))[0]
    token.expires_at = in_the_past()
    await db_session.flush()

    response = await client.post("/auth/refresh")

    assert response.status_code == 401
    assert all(t.revoked_at is None for t in await all_tokens(db_session))


async def test_an_unknown_token_revokes_nothing(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    await register(client)
    await login(client)

    response = await client.post("/auth/refresh", headers=presenting("not-a-real-token"))

    assert response.status_code == 401
    assert all(t.revoked_at is None for t in await all_tokens(db_session))


async def test_a_deleted_user_cannot_refresh(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    await register(client)
    await login(client)
    await db_session.execute(delete(User))
    await db_session.flush()

    response = await client.post("/auth/refresh")

    assert response.status_code == 401
    assert await all_tokens(db_session) == []


async def test_refresh_without_a_cookie_is_401(client: httpx.AsyncClient) -> None:
    response = await client.post("/auth/refresh")

    assert response.status_code == 401


async def test_an_access_token_in_the_cookie_is_401(client: httpx.AsyncClient) -> None:
    user_id = (await register(client)).json()["id"]

    response = await client.post("/auth/refresh", headers=presenting(create_access_token(user_id)))

    assert response.status_code == 401


async def test_every_rejection_looks_identical(client: httpx.AsyncClient) -> None:
    await register(client)
    no_cookie = await client.post("/auth/refresh")
    unknown = await client.post("/auth/refresh", headers=presenting("not-a-real-token"))

    assert no_cookie.status_code == unknown.status_code == 401
    assert no_cookie.json() == unknown.json()


async def test_a_rejected_refresh_clears_the_cookie(client: httpx.AsyncClient) -> None:
    response = await client.post("/auth/refresh", headers=presenting("not-a-real-token"))

    assert response.status_code == 401
    cookie_header = response.headers["set-cookie"]
    assert "Max-Age=0" in cookie_header
    assert "Path=/" in cookie_header
    assert "Path=/auth" not in cookie_header
    # A __Host- violation here would make the cookie un-clearable, and the test client
    # does not enforce prefixes, so the shape has to be asserted directly.
    assert "Secure" in cookie_header
    assert "Domain=" not in cookie_header


async def test_logout_kills_the_session(client: httpx.AsyncClient) -> None:
    await register(client)
    await login(client)

    logout = await client.post("/auth/logout")

    assert logout.status_code == 204
    assert "Max-Age=0" in logout.headers["set-cookie"]


async def test_refresh_after_logout_is_401(client: httpx.AsyncClient) -> None:
    await register(client)
    raw = (await login(client)).cookies["__Host-refresh_token"]
    await client.post("/auth/logout")

    response = await client.post("/auth/refresh", headers=presenting(raw))

    assert response.status_code == 401


async def test_logout_is_idempotent(client: httpx.AsyncClient) -> None:
    await register(client)
    raw = (await login(client)).cookies["__Host-refresh_token"]

    assert (await client.post("/auth/logout", headers=presenting(raw))).status_code == 204
    assert (await client.post("/auth/logout", headers=presenting(raw))).status_code == 204


async def test_logout_without_a_cookie_is_still_204(client: httpx.AsyncClient) -> None:
    assert (await client.post("/auth/logout")).status_code == 204


async def test_logout_with_an_unknown_token_is_still_204(client: httpx.AsyncClient) -> None:
    response = await client.post("/auth/logout", headers=presenting("not-a-real-token"))

    assert response.status_code == 204


async def test_logout_of_one_device_leaves_the_other_alive(client: httpx.AsyncClient) -> None:
    await register(client)
    phone_raw = (await login(client)).cookies["__Host-refresh_token"]
    laptop_raw = (await login(client)).cookies["__Host-refresh_token"]

    await client.post("/auth/logout", headers=presenting(phone_raw))

    laptop = await client.post("/auth/refresh", headers=presenting(laptop_raw))
    assert laptop.status_code == 200

    phone = await client.post("/auth/refresh", headers=presenting(phone_raw))
    assert phone.status_code == 401
