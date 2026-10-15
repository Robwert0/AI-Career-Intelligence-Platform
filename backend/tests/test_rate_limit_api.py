import time
import uuid

import httpx
import pytest
from fakes import AllowAllLimiter, UnavailableLimiter
from fastapi.routing import APIRoute

from app.core import policies
from app.core.rate_limiter import Policy
from app.core.redis import create_redis
from app.deps import get_global_identity, get_limiter
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


async def test_logout_is_limited_per_ip(limited_client: httpx.AsyncClient) -> None:
    statuses = [(await limited_client.post("/auth/logout")).status_code for _ in range(11)]
    assert statuses == [204] * 10 + [429]


def test_every_route_that_does_work_carries_a_rate_limit() -> None:
    # A route can only ship unlimited by being added here, in a reviewable diff.
    exempt = {("GET", "/health")}
    unlimited = []
    for included in app.routes:
        router = getattr(included, "original_router", None)
        context = getattr(included, "include_context", None)
        if router is None or context is None:
            continue
        for route in router.routes:
            if not isinstance(route, APIRoute):
                continue
            path = f"{context.prefix}{route.path}"
            attached = {getattr(d.dependency, "__name__", "") for d in route.dependencies}
            limited = attached & {"by_ip", "by_user", "by_global"}
            for method in route.methods or set():
                if not limited and (method, path) not in exempt:
                    unlimited.append((method, path))
    assert unlimited == []


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


def _bucket(policy: Policy, identity: str) -> str:
    return f"rl:{policy.name}:{identity}"


async def _drain(policy: Policy, identity: str) -> None:
    redis = create_redis()
    try:
        await redis.hset(_bucket(policy, identity), mapping={"tokens": 0, "ts": time.time()})
        await redis.expire(_bucket(policy, identity), 600)
    finally:
        await redis.aclose()


def _global_identity() -> str:
    identity: str = app.dependency_overrides[get_global_identity]()
    return identity


async def test_chat_is_capped_per_user_per_day(limited_client: httpx.AsyncClient) -> None:
    registered = await limited_client.post(
        "/auth/register", json={"email": EMAIL, "password": PASSWORD}
    )
    login = await limited_client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    await _drain(policies.CHAT_USER_DAILY, registered.json()["id"])

    response = await limited_client.post("/chat", json={"message": "hi"}, headers=headers)

    assert response.status_code == 429
    assert int(response.headers["Retry-After"]) > 60


async def test_registration_has_a_ceiling_across_every_ip(
    limited_client: httpx.AsyncClient,
) -> None:
    await _drain(policies.REGISTER_GLOBAL, _global_identity())

    response = await limited_client.post(
        "/auth/register", json={"email": EMAIL, "password": PASSWORD}
    )

    assert response.status_code == 429


async def test_a_denied_ip_does_not_spend_the_global_registration_budget(
    limited_client: httpx.AsyncClient,
) -> None:
    for attempt in range(5):
        await limited_client.post(
            "/auth/register", json={"email": f"{attempt}{EMAIL}", "password": PASSWORD}
        )

    redis = create_redis()
    try:
        left = await redis.hget(_bucket(policies.REGISTER_GLOBAL, _global_identity()), "tokens")
    finally:
        await redis.aclose()
    assert left is not None
    spent = policies.REGISTER_GLOBAL.capacity - float(left)
    assert spent == pytest.approx(policies.REGISTER.capacity, abs=0.1)


async def _login(client: httpx.AsyncClient) -> tuple[str, dict[str, str]]:
    registered = await client.post("/auth/register", json={"email": EMAIL, "password": PASSWORD})
    login = await client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})
    return registered.json()["id"], {"Authorization": f"Bearer {login.json()['access_token']}"}


async def test_job_intake_is_capped_per_user_per_day(limited_client: httpx.AsyncClient) -> None:
    user_id, headers = await _login(limited_client)
    await _drain(policies.MATCH_JOB_USER_DAILY, user_id)

    response = await limited_client.post(
        "/match/jobs", json={"text": "We build payment systems in Go. " * 5}, headers=headers
    )

    assert response.status_code == 429
    assert int(response.headers["Retry-After"]) > 60


@pytest.mark.parametrize("path", ["/match/analyses", f"/match/analyses/{uuid.uuid4()}/retry"])
async def test_analyses_are_capped_per_user_per_day(
    limited_client: httpx.AsyncClient, path: str
) -> None:
    user_id, headers = await _login(limited_client)
    await _drain(policies.MATCH_ANALYSIS_USER_DAILY, user_id)

    response = await limited_client.post(path, headers=headers)

    assert response.status_code == 429
    assert int(response.headers["Retry-After"]) > 3600


async def test_continuing_an_analysis_is_capped_per_user_per_day(
    limited_client: httpx.AsyncClient,
) -> None:
    user_id, headers = await _login(limited_client)
    await _drain(policies.MATCH_CONTINUE_USER_DAILY, user_id)

    response = await limited_client.post(
        f"/match/analyses/{uuid.uuid4()}/continue", headers=headers
    )

    assert response.status_code == 429
    assert int(response.headers["Retry-After"]) > 3600
