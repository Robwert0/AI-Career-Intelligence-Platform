import uuid

import httpx
from fakes import AllowAllLimiter, UnavailableLimiter

from app.deps import get_limiter
from app.main import app

EMAIL = "limited@test.dev"
PASSWORD = "supersecret1"
WRONG = {"email": "nobody@example.com", "password": "wrong-password-12"}


async def _drain_login(client: httpx.AsyncClient, attempts: int = 6) -> list[httpx.Response]:
    return [await client.post("/auth/login", json=WRONG) for _ in range(attempts)]


async def test_login_is_limited_per_ip(limited_client: httpx.AsyncClient) -> None:
    statuses = [response.status_code for response in await _drain_login(limited_client)]
    assert statuses == [401, 401, 401, 401, 401, 429]


async def test_a_spoofed_x_forwarded_for_cannot_move_the_bucket(
    limited_client: httpx.AsyncClient,
) -> None:
    for hop in range(6):
        response = await limited_client.post(
            "/auth/login", json=WRONG, headers={"X-Forwarded-For": f"9.9.9.{hop}"}
        )
    assert response.status_code == 429


async def test_the_429_carries_a_retry_after_header(limited_client: httpx.AsyncClient) -> None:
    denied = (await _drain_login(limited_client))[-1]
    assert denied.status_code == 429
    assert int(denied.headers["Retry-After"]) >= 1


async def test_login_and_register_have_separate_budgets(
    limited_client: httpx.AsyncClient,
) -> None:
    assert (await _drain_login(limited_client))[-1].status_code == 429
    response = await limited_client.post(
        "/auth/register", json={"email": EMAIL, "password": PASSWORD}
    )
    assert response.status_code != 429


async def test_users_me_fires_both_an_ip_policy_and_a_user_policy(
    client: httpx.AsyncClient, allow_all_limiter: AllowAllLimiter
) -> None:
    await client.post("/auth/register", json={"email": EMAIL, "password": PASSWORD})
    login = await client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})
    token = login.json()["access_token"]
    allow_all_limiter.calls.clear()

    response = await client.get("/users/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    fired = dict(allow_all_limiter.calls)
    assert set(fired) == {"me_ip", "me_user"}
    assert fired["me_ip"].count(".") == 3
    assert uuid.UUID(fired["me_user"])


async def test_health_is_never_limited(limited_client: httpx.AsyncClient) -> None:
    statuses = {(await limited_client.get("/health")).status_code for _ in range(200)}
    assert statuses == {200}


async def test_redis_down_fails_closed_and_the_route_body_never_runs(
    client: httpx.AsyncClient,
) -> None:
    await client.post("/auth/register", json={"email": EMAIL, "password": PASSWORD})
    app.dependency_overrides[get_limiter] = UnavailableLimiter

    response = await client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})

    assert response.status_code == 503
    assert "set-cookie" not in response.headers
    assert "redis" not in response.text.lower()


async def test_health_still_answers_when_redis_is_down(client: httpx.AsyncClient) -> None:
    app.dependency_overrides[get_limiter] = UnavailableLimiter
    assert (await client.get("/health")).status_code == 200
