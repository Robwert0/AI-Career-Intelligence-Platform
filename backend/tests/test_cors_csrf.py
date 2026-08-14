import httpx

from app.core.config import settings

ALLOWED = settings.cors_allowed_origins[0]
DISALLOWED = "https://blog.attacker.example"


async def test_preflight_is_answered_for_an_allowed_origin(client: httpx.AsyncClient) -> None:
    response = await client.options(
        "/auth/refresh",
        headers={"Origin": ALLOWED, "Access-Control-Request-Method": "POST"},
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ALLOWED
    assert response.headers["access-control-allow-credentials"] == "true"


async def test_preflight_is_not_answered_for_a_disallowed_origin(
    client: httpx.AsyncClient,
) -> None:
    response = await client.options(
        "/auth/refresh",
        headers={"Origin": DISALLOWED, "Access-Control-Request-Method": "POST"},
    )

    assert "access-control-allow-origin" not in response.headers


async def test_a_real_request_carries_the_cors_headers(client: httpx.AsyncClient) -> None:
    without_origin = await client.post(
        "/auth/login", json={"email": "x@y.dev", "password": "wrongpass1"}
    )

    assert without_origin.headers.get("access-control-allow-origin") is None

    with_origin = await client.post(
        "/auth/login",
        json={"email": "x@y.dev", "password": "wrongpass1"},
        headers={"Origin": ALLOWED},
    )

    assert with_origin.headers["access-control-allow-origin"] == ALLOWED
    assert with_origin.headers["access-control-allow-credentials"] == "true"
