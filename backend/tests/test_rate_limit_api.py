import asyncio
import logging
import math
import time
import uuid

import httpx
import pytest
from fakes import (
    AllowAllLimiter,
    AuthServiceBrokeError,
    BrokenRegistrar,
    PolicyUnavailableLimiter,
    RefundUnavailableLimiter,
    SlowRegistrar,
    UnavailableLimiter,
)
from fastapi.routing import APIRoute
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import policies
from app.core.rate_limiter import Policy
from app.core.redis import create_redis
from app.deps import get_auth_service, get_global_identity, get_limiter
from app.main import app
from app.repositories import UserRepository

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


async def _spent(policy: Policy) -> float:
    redis = create_redis()
    try:
        left = await redis.hget(_bucket(policy, _global_identity()), "tokens")
    finally:
        await redis.aclose()
    return 0.0 if left is None else policy.capacity - float(left)


async def _global_registrations_spent() -> float:
    return await _spent(policies.REGISTER_GLOBAL)


async def _set_tokens(policy: Policy, identity: str, tokens: float) -> None:
    redis = create_redis()
    try:
        await redis.hset(_bucket(policy, identity), mapping={"tokens": tokens, "ts": time.time()})
        await redis.expire(_bucket(policy, identity), 600)
    finally:
        await redis.aclose()


def _ip_block() -> str:
    # Per-IP buckets outlive a test run, so each test needs addresses no earlier run used.
    a, b = uuid.uuid4().bytes[:2]
    return f"10.{a}.{b}."


def _client_from(block: str, octet: int) -> httpx.AsyncClient:
    # Shares the overrides limited_client installed, from a distinct address per client.
    transport = httpx.ASGITransport(app=app, client=(f"{block}{octet}", 123))
    return httpx.AsyncClient(transport=transport, base_url="https://test")


async def _register_burst(count: int) -> list[int]:
    block = _ip_block()
    clients = [_client_from(block, octet) for octet in range(count)]
    try:
        responses = await asyncio.gather(
            *(
                c.post("/auth/register", json={"email": f"{i}{EMAIL}", "password": PASSWORD})
                for i, c in enumerate(clients)
            )
        )
    finally:
        await asyncio.gather(*(c.aclose() for c in clients))
    return [response.status_code for response in responses]


def _ipv6_client(prefix: str, host: str) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app, client=(f"{prefix}:{host}", 123))
    return httpx.AsyncClient(transport=transport, base_url="https://test")


async def test_ipv6_clients_in_one_64_share_a_register_bucket(
    limited_client: httpx.AsyncClient,
) -> None:
    a, b = uuid.uuid4().hex[:4], uuid.uuid4().hex[:4]
    prefix = f"2001:db8:{a}:{b}"
    async with _ipv6_client(prefix, "0:0:0:1") as first:
        spent = [
            (await first.post("/auth/register", json={"email": EMAIL})).status_code
            for _ in range(policies.REGISTER.capacity)
        ]
    async with _ipv6_client(prefix, "dead:beef:0:2") as neighbour:
        refused = await neighbour.post("/auth/register", json={"email": EMAIL})
    async with _ipv6_client(f"2001:db8:{a}:{int(b, 16) ^ 1:x}", "0:0:0:1") as elsewhere:
        other_64 = await elsewhere.post("/auth/register", json={"email": EMAIL})

    assert spent == [422] * policies.REGISTER.capacity
    assert refused.status_code == 429
    assert other_64.status_code == 422


async def test_registration_has_a_ceiling_across_every_ip(
    limited_client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    await _drain(policies.REGISTER_GLOBAL, _global_identity())

    response = await limited_client.post(
        "/auth/register", json={"email": EMAIL, "password": PASSWORD}
    )

    assert response.status_code == 429
    assert int(response.headers["Retry-After"]) >= 1
    assert await UserRepository(db_session).get_user_by_email(EMAIL) is None


async def test_a_denied_ip_does_not_spend_the_global_registration_budget(
    limited_client: httpx.AsyncClient,
) -> None:
    for attempt in range(5):
        await limited_client.post(
            "/auth/register", json={"email": f"{attempt}{EMAIL}", "password": PASSWORD}
        )

    assert await _global_registrations_spent() == pytest.approx(policies.REGISTER.capacity, abs=0.1)
    assert await _spent(policies.REGISTER_ATTEMPTS_GLOBAL) == pytest.approx(
        policies.REGISTER.capacity, abs=0.2
    )


async def test_a_concurrent_burst_cannot_overrun_the_last_account_token(
    limited_client: httpx.AsyncClient,
) -> None:
    registrar = SlowRegistrar()
    app.dependency_overrides[get_auth_service] = lambda: registrar
    await _set_tokens(policies.REGISTER_GLOBAL, _global_identity(), 1)

    statuses = await _register_burst(12)

    assert sorted(statuses) == [201] + [429] * 11
    assert len(registrar.created) == 1


async def test_a_burst_larger_than_the_ceiling_creates_at_most_capacity_accounts(
    limited_client: httpx.AsyncClient,
) -> None:
    registrar = SlowRegistrar()
    app.dependency_overrides[get_auth_service] = lambda: registrar
    capacity = policies.REGISTER_GLOBAL.capacity

    statuses = await _register_burst(capacity + 10)

    assert statuses.count(201) == capacity
    assert statuses.count(429) == 10
    assert len(registrar.created) == capacity


async def test_a_created_account_spends_one_global_registration(
    limited_client: httpx.AsyncClient,
) -> None:
    response = await limited_client.post(
        "/auth/register", json={"email": EMAIL, "password": PASSWORD}
    )

    assert response.status_code == 201
    assert await _global_registrations_spent() == pytest.approx(1, abs=0.1)


async def test_invalid_bodies_do_not_spend_the_global_registration_budget(
    limited_client: httpx.AsyncClient,
) -> None:
    statuses = [
        (await limited_client.post("/auth/register", json={"email": EMAIL})).status_code
        for _ in range(policies.REGISTER.capacity)
    ]

    assert statuses == [422] * policies.REGISTER.capacity
    assert await _global_registrations_spent() == 0.0


async def test_duplicates_spend_attempts_but_refund_the_account_token(
    limited_client: httpx.AsyncClient,
) -> None:
    statuses = [
        (
            await limited_client.post("/auth/register", json={"email": EMAIL, "password": PASSWORD})
        ).status_code
        for _ in range(policies.REGISTER.capacity)
    ]

    assert statuses == [201] + [409] * (policies.REGISTER.capacity - 1)
    assert await _global_registrations_spent() == pytest.approx(1, abs=0.1)
    assert await _spent(policies.REGISTER_ATTEMPTS_GLOBAL) == pytest.approx(
        policies.REGISTER.capacity, abs=0.2
    )


async def test_probing_existing_emails_is_capped_across_every_ip(
    limited_client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    await UserRepository(db_session).create_user(email=EMAIL, hashed_password="not-a-real-hash")
    attempts = policies.REGISTER_ATTEMPTS_GLOBAL.capacity
    per_ip = policies.REGISTER.capacity
    block = _ip_block()
    statuses: list[int] = []
    for octet in range(math.ceil(attempts / per_ip)):
        async with _client_from(block, octet) as c:
            for _ in range(min(per_ip, attempts - len(statuses))):
                body = {"email": EMAIL, "password": PASSWORD}
                statuses.append((await c.post("/auth/register", json=body)).status_code)

    async with _client_from(block, 255) as fresh_ip:
        refused = await fresh_ip.post("/auth/register", json={"email": EMAIL, "password": PASSWORD})

    assert statuses == [409] * attempts
    assert refused.status_code == 429
    assert await _global_registrations_spent() == pytest.approx(0, abs=0.1)


async def test_a_refused_ip_does_not_spend_the_global_attempts(
    limited_client: httpx.AsyncClient,
) -> None:
    statuses = [
        (await limited_client.post("/auth/register", json={"email": EMAIL})).status_code
        for _ in range(policies.REGISTER.capacity + 2)
    ]

    assert statuses == [422] * policies.REGISTER.capacity + [429] * 2
    assert await _spent(policies.REGISTER_ATTEMPTS_GLOBAL) == pytest.approx(
        policies.REGISTER.capacity, abs=0.2
    )


async def test_a_failed_registration_refunds_the_account_token(
    limited_client: httpx.AsyncClient,
) -> None:
    app.dependency_overrides[get_auth_service] = BrokenRegistrar

    with pytest.raises(AuthServiceBrokeError):
        await limited_client.post("/auth/register", json={"email": EMAIL, "password": PASSWORD})

    assert await _global_registrations_spent() == pytest.approx(0, abs=0.1)
    assert await _spent(policies.REGISTER_ATTEMPTS_GLOBAL) == pytest.approx(1, abs=0.2)


async def test_a_full_global_ceiling_warns_once_without_naming_the_registrant(
    limited_client: httpx.AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    await _drain(policies.REGISTER_GLOBAL, _global_identity())

    with caplog.at_level(logging.DEBUG, logger="app.deps"):
        for attempt in range(policies.REGISTER.capacity):
            await limited_client.post(
                "/auth/register", json={"email": f"{attempt}{EMAIL}", "password": PASSWORD}
            )

    refusals = [r for r in caplog.records if policies.REGISTER_GLOBAL.name in r.getMessage()]
    assert [r.levelno for r in refusals] == [logging.WARNING] + [logging.DEBUG] * (
        policies.REGISTER.capacity - 1
    )
    assert not any(EMAIL in r.getMessage() or "10." in r.getMessage() for r in refusals)


async def test_a_full_attempts_ceiling_warns_once_without_naming_the_registrant(
    limited_client: httpx.AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    await _drain(policies.REGISTER_ATTEMPTS_GLOBAL, _global_identity())

    with caplog.at_level(logging.DEBUG, logger="app.deps"):
        statuses = [
            (
                await limited_client.post(
                    "/auth/register", json={"email": f"{attempt}{EMAIL}", "password": PASSWORD}
                )
            ).status_code
            for attempt in range(policies.REGISTER.capacity)
        ]

    name = policies.REGISTER_ATTEMPTS_GLOBAL.name
    refusals = [r for r in caplog.records if name in r.getMessage()]
    assert statuses == [429] * policies.REGISTER.capacity
    assert [r.levelno for r in refusals] == [logging.WARNING] + [logging.DEBUG] * (
        policies.REGISTER.capacity - 1
    )
    assert not any(EMAIL in r.getMessage() or "10." in r.getMessage() for r in refusals)


async def test_redis_down_at_the_account_ceiling_fails_registration_closed(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    app.dependency_overrides[get_limiter] = lambda: PolicyUnavailableLimiter(
        policies.REGISTER_GLOBAL.name
    )

    response = await client.post("/auth/register", json={"email": EMAIL, "password": PASSWORD})

    assert response.status_code == 503
    assert "redis" not in response.text.lower()
    assert await UserRepository(db_session).get_user_by_email(EMAIL) is None


async def test_redis_down_at_refund_still_answers_the_duplicate_with_409(
    client: httpx.AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    await client.post("/auth/register", json={"email": EMAIL, "password": PASSWORD})
    app.dependency_overrides[get_limiter] = RefundUnavailableLimiter

    with caplog.at_level(logging.ERROR, logger="app.deps"):
        response = await client.post("/auth/register", json={"email": EMAIL, "password": PASSWORD})

    assert response.status_code == 409
    failures = [r for r in caplog.records if "refund failed" in r.getMessage()]
    assert len(failures) == 1
    assert EMAIL not in failures[0].getMessage()


async def test_redis_down_at_refund_lets_the_original_error_surface(
    client: httpx.AsyncClient,
) -> None:
    app.dependency_overrides[get_limiter] = RefundUnavailableLimiter
    app.dependency_overrides[get_auth_service] = BrokenRegistrar

    with pytest.raises(AuthServiceBrokeError):
        await client.post("/auth/register", json={"email": EMAIL, "password": PASSWORD})


async def test_the_account_ceiling_is_taken_after_validation_and_refunded_only_on_failure(
    client: httpx.AsyncClient, allow_all_limiter: AllowAllLimiter
) -> None:
    await client.post("/auth/register", json={"email": EMAIL})
    taken = [name for name, _ in allow_all_limiter.calls]
    assert policies.REGISTER_GLOBAL.name not in taken
    assert policies.REGISTER_ATTEMPTS_GLOBAL.name in taken

    await client.post("/auth/register", json={"email": EMAIL, "password": PASSWORD})
    assert allow_all_limiter.refunded == []

    await client.post("/auth/register", json={"email": EMAIL, "password": PASSWORD})
    taken = [name for name, _ in allow_all_limiter.calls]
    assert taken.count(policies.REGISTER_GLOBAL.name) == 2
    assert allow_all_limiter.refunded == [policies.REGISTER_GLOBAL.name]


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
