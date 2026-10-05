import uuid
from typing import get_args

import httpx
import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.models.user import USER_ROLES
from app.repositories import UserRepository
from app.schemas.auth import UserRole


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


def _body(**extra: object) -> dict[str, object]:
    return {"email": f"{uuid.uuid4().hex[:8]}@test.dev", "password": "supersecret1", **extra}


def test_the_api_roles_match_the_database_roles() -> None:
    assert get_args(UserRole) == USER_ROLES


async def test_register_stores_company_and_role(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    response = await client.post("/auth/register", json=_body(company="  Acme  ", role="recruiter"))

    assert response.status_code == 201
    body = response.json()
    assert body["company"] == "Acme"
    assert body["role"] == "recruiter"
    assert body["is_admin"] is False


async def test_register_without_profile_still_works(client: httpx.AsyncClient) -> None:
    response = await client.post("/auth/register", json=_body())

    assert response.status_code == 201
    assert response.json()["company"] is None
    assert response.json()["role"] is None


async def test_a_blank_company_is_stored_as_null(client: httpx.AsyncClient) -> None:
    response = await client.post("/auth/register", json=_body(company="   "))

    assert response.status_code == 201
    assert response.json()["company"] is None


async def test_an_unknown_role_is_rejected(client: httpx.AsyncClient) -> None:
    response = await client.post("/auth/register", json=_body(role="ceo"))

    assert response.status_code == 422


async def test_a_company_over_100_characters_is_rejected(client: httpx.AsyncClient) -> None:
    response = await client.post("/auth/register", json=_body(company="x" * 101))

    assert response.status_code == 422


async def test_a_forged_admin_flag_is_ignored(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    body = _body(is_admin=True)
    response = await client.post("/auth/register", json=body)

    assert response.status_code == 201
    assert response.json()["is_admin"] is False
    stored = await UserRepository(db_session).get_user_by_email(str(body["email"]))
    assert stored is not None and stored.is_admin is False
