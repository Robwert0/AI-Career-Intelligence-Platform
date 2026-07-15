import httpx

from app.core.security import decode_token

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


async def test_access_token_identifies_registered_user(client: httpx.AsyncClient) -> None:
    user_id = (await register(client)).json()["id"]
    access_token = (await login(client)).json()["access_token"]

    payload = decode_token(access_token, expected_type="access")
    assert payload["sub"] == user_id
