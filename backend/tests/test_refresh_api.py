import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_refresh_token
from app.models import RefreshToken

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


async def test_login_persists_exactly_one_token(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    await register(client)
    await login(client)

    assert len(await all_tokens(db_session)) == 1


async def test_login_cookie_is_opaque_not_a_jwt(client: httpx.AsyncClient) -> None:
    await register(client)
    raw = (await login(client)).cookies["refresh_token"]

    assert "." not in raw
    assert len(raw) >= 43


async def test_only_the_hash_of_the_token_is_stored(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    await register(client)
    raw = (await login(client)).cookies["refresh_token"]

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
