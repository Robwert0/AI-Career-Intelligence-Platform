import uuid

import httpx
import pytest

from app.core.security import decode_token
from app.repositories import UserRepository

EMAIL = "robert@test.dev"
PASSWORD = "supersecret1"


async def register(client: httpx.AsyncClient) -> httpx.Response:
    return await client.post("/auth/register", json={"email": EMAIL, "password": PASSWORD})


async def login(client: httpx.AsyncClient, password: str = PASSWORD) -> httpx.Response:
    return await client.post("/auth/login", json={"email": EMAIL, "password": password})


async def test_register_creates_user(client: httpx.AsyncClient) -> None:
    response = await register(client)

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == EMAIL
    assert "hashed_password" not in body


async def test_register_duplicate_email_conflicts(client: httpx.AsyncClient) -> None:
    await register(client)
    response = await register(client)

    assert response.status_code == 409


async def test_register_conflicts_when_precheck_misses(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    await register(client)

    async def blind(self: UserRepository, email: str) -> None:
        """Simulates the loser of a register race: its SELECT ran before the winner's INSERT."""
        return None

    monkeypatch.setattr(UserRepository, "get_user_by_email", blind)

    response = await register(client)

    assert response.status_code == 409


async def test_login_returns_access_token_only(client: httpx.AsyncClient) -> None:
    await register(client)
    response = await login(client)

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert "access_token" in body
    assert "refresh_token" not in body


async def test_login_sets_refresh_cookie(client: httpx.AsyncClient) -> None:
    await register(client)
    response = await login(client)

    assert response.cookies.get("refresh_token")
    cookie_header = response.headers["set-cookie"]
    assert "HttpOnly" in cookie_header
    assert "SameSite=strict" in cookie_header
    assert "Path=/auth" in cookie_header
    assert "Secure" in cookie_header


async def test_login_failures_are_indistinguishable(client: httpx.AsyncClient) -> None:
    await register(client)
    wrong_password = await login(client, password="wrongwrong1")
    unknown_email = await client.post(
        "/auth/login", json={"email": "ghost@test.dev", "password": PASSWORD}
    )

    assert wrong_password.status_code == 401
    assert unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()


async def test_access_token_identifies_registered_user(
    client: httpx.AsyncClient,
) -> None:
    user_id = (await register(client)).json()["id"]
    access_token = (await login(client)).json()["access_token"]

    payload = decode_token(access_token, expected_type="access")
    assert payload["sub"] == user_id


async def test_me_returns_the_authenticated_user(client: httpx.AsyncClient) -> None:
    registered = (await register(client)).json()
    access_token = (await login(client)).json()["access_token"]

    response = await client.get("/users/me", headers={"Authorization": f"Bearer {access_token}"})

    assert response.status_code == 200
    assert response.json()["id"] == registered["id"]
    assert response.json()["email"] == EMAIL


async def test_me_without_a_token_is_401(client: httpx.AsyncClient) -> None:
    response = await client.get("/users/me")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


async def test_me_with_a_non_bearer_scheme_is_401(client: httpx.AsyncClient) -> None:
    response = await client.get("/users/me", headers={"Authorization": "Basic cm9iZXJ0"})

    assert response.status_code == 401


async def test_me_with_a_garbage_token_is_401(client: httpx.AsyncClient) -> None:
    response = await client.get("/users/me", headers={"Authorization": "Bearer not.a.jwt"})

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


async def test_me_rejects_a_refresh_token(client: httpx.AsyncClient) -> None:
    await register(client)
    refresh_token = (await login(client)).cookies["refresh_token"]

    response = await client.get("/users/me", headers={"Authorization": f"Bearer {refresh_token}"})

    assert response.status_code == 401


async def test_me_rejects_a_token_whose_user_is_gone(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    await register(client)
    access_token = (await login(client)).json()["access_token"]

    async def deleted(self: UserRepository, user_id: uuid.UUID) -> None:
        """Simulates a token that outlived the account it names."""
        return None

    monkeypatch.setattr(UserRepository, "get_user_by_id", deleted)

    response = await client.get("/users/me", headers={"Authorization": f"Bearer {access_token}"})

    assert response.status_code == 401


async def test_me_rejects_a_non_string_subject(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    await register(client)
    access_token = (await login(client)).json()["access_token"]

    def malformed(token: str, expected_type: str) -> dict[str, object]:
        """pyjwt rejects a non-str `sub` itself; bypass it to pin our own handling."""
        return {"sub": 12345, "type": expected_type, "iat": 0, "exp": 0}

    monkeypatch.setattr("app.services.auth_service.decode_token", malformed)

    response = await client.get("/users/me", headers={"Authorization": f"Bearer {access_token}"})

    assert response.status_code == 401


async def test_login_overlong_password_is_not_a_500(client: httpx.AsyncClient) -> None:
    await register(client)
    long_password = await login(client, password="*" * 100)

    assert long_password.status_code != 500
    assert long_password.status_code == 422


async def test_login_multibyte_password_is_not_a_500(client: httpx.AsyncClient) -> None:
    await register(client)
    long_password = await login(client, password="é" * 72)

    assert long_password.status_code == 422


async def test_register_multibyte_password_is_rejected(
    client: httpx.AsyncClient,
) -> None:
    response = await client.post("/auth/register", json={"email": EMAIL, "password": "é" * 72})

    assert response.status_code == 422


async def test_validation_error_does_not_echo_password(client: httpx.AsyncClient) -> None:
    secret = "é" * 72
    response = await client.post("/auth/register", json={"email": EMAIL, "password": secret})

    assert response.status_code == 422
    assert secret not in response.text


async def test_login_unknown_email_still_hashes(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    compared_against: list[str] = []

    def spy(plain_password: str, hashed_password: str) -> bool:
        compared_against.append(hashed_password)
        return False

    monkeypatch.setattr("app.services.auth_service.verify_password", spy)

    response = await client.post(
        "/auth/login", json={"email": "ghost@test.dev", "password": PASSWORD}
    )

    assert response.status_code == 401
    assert compared_against, "unknown email must still pay the bcrypt cost"
    assert compared_against[0].startswith("$2b$"), "must compare against a real bcrypt hash"


async def test_validation_error_still_explains_the_problem(client: httpx.AsyncClient) -> None:
    response = await client.post("/auth/register", json={"email": EMAIL, "password": "short"})

    assert response.status_code == 422
    error = response.json()["detail"][0]
    assert error["loc"] == ["body", "password"]
    assert error["msg"]


async def test_refresh_cookie_is_replayed_to_the_server(client: httpx.AsyncClient) -> None:
    """A Secure cookie is only sent over https, so the fixture's scheme is load-bearing."""
    await register(client)
    await login(client)

    request = client.build_request("POST", "/auth/refresh")
    client.cookies.set_cookie_header(request)

    assert "refresh_token" in request.headers.get("cookie", "")
