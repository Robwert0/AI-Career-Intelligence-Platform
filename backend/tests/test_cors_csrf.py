import re

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import hash_refresh_token
from app.main import app
from app.models import RefreshToken

ALLOWED = settings.cors_allowed_origins[0]
DISALLOWED = "https://blog.attacker.example"
EMAIL = "csrf@test.dev"
PASSWORD = "supersecret1"

# Spelled out rather than imported from app.deps on purpose: this is the spec the guard must meet.
# Importing the real set would make the sweep below shrink in lockstep with a mistaken widening of
# it — adding "POST" to the app's exemptions would silently stop testing every POST route.
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


async def register(client: httpx.AsyncClient) -> httpx.Response:
    return await client.post("/auth/register", json={"email": EMAIL, "password": PASSWORD})


async def login(client: httpx.AsyncClient) -> httpx.Response:
    return await client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})


async def all_tokens(db_session: AsyncSession) -> list[RefreshToken]:
    db_session.expire_all()
    result = await db_session.execute(select(RefreshToken))
    return list(result.scalars().all())


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


async def test_refresh_accepts_an_allowlisted_origin(client: httpx.AsyncClient) -> None:
    await register(client)
    await login(client)

    response = await client.post("/auth/refresh", headers={"Origin": ALLOWED})

    assert response.status_code == 200


async def test_refresh_without_an_origin_still_works(client: httpx.AsyncClient) -> None:
    await register(client)
    await login(client)

    response = await client.post("/auth/refresh")

    assert response.status_code == 200


async def test_refresh_from_a_disallowed_origin_does_not_rotate(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    await register(client)
    raw = (await login(client)).cookies["__Host-refresh_token"]

    response = await client.post("/auth/refresh", headers={"Origin": DISALLOWED})

    assert response.status_code == 403
    tokens = await all_tokens(db_session)
    assert len(tokens) == 1
    assert tokens[0].token_hash == hash_refresh_token(raw)
    assert tokens[0].used_at is None


async def test_a_forbidden_refresh_does_not_clear_the_cookie(client: httpx.AsyncClient) -> None:
    await register(client)
    await login(client)

    response = await client.post("/auth/refresh", headers={"Origin": DISALLOWED})

    assert response.status_code == 403
    assert "set-cookie" not in response.headers


async def test_logout_from_a_disallowed_origin_does_not_revoke(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    await register(client)
    await login(client)

    response = await client.post("/auth/logout", headers={"Origin": DISALLOWED})

    assert response.status_code == 403
    assert all(token.revoked_at is None for token in await all_tokens(db_session))


async def test_login_from_a_disallowed_origin_issues_no_cookie(
    client: httpx.AsyncClient,
) -> None:
    """Login-CSRF: __Host- does not stop the API itself minting a session for an attacker."""
    await register(client)

    response = await client.post(
        "/auth/login",
        json={"email": EMAIL, "password": PASSWORD},
        headers={"Origin": DISALLOWED},
    )

    assert response.status_code == 403
    assert "set-cookie" not in response.headers


async def test_login_from_the_apis_own_origin_is_allowed(client: httpx.AsyncClient) -> None:
    """Swagger at /docs POSTs same-origin, and the CORS allowlist never contains our own origin."""
    await register(client)
    same_origin = str(client.base_url)

    assert same_origin not in settings.cors_allowed_origins

    response = await client.post(
        "/auth/login",
        json={"email": EMAIL, "password": PASSWORD},
        headers={"Origin": same_origin},
    )

    assert response.status_code == 200
    assert response.cookies.get("__Host-refresh_token")


async def test_refresh_from_the_apis_own_origin_is_allowed(client: httpx.AsyncClient) -> None:
    await register(client)
    await login(client)

    response = await client.post("/auth/refresh", headers={"Origin": str(client.base_url)})

    assert response.status_code == 200


async def test_register_from_a_disallowed_origin_is_403(
    client: httpx.AsyncClient, db_session: AsyncSession
) -> None:
    response = await client.post(
        "/auth/register",
        json={"email": EMAIL, "password": PASSWORD},
        headers={"Origin": DISALLOWED},
    )

    assert response.status_code == 403
    assert await all_tokens(db_session) == []


async def test_login_from_an_allowlisted_origin_still_issues_a_cookie(
    client: httpx.AsyncClient,
) -> None:
    await register(client)

    response = await client.post(
        "/auth/login",
        json={"email": EMAIL, "password": PASSWORD},
        headers={"Origin": ALLOWED},
    )

    assert response.status_code == 200
    assert response.cookies.get("__Host-refresh_token")


_HTTP_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH", "DELETE", "TRACE"})


def _state_changing_routes() -> list[tuple[str, str]]:
    # app.routes is not a flat list of endpoints — FastAPI nests each included router behind a
    # private wrapper — so the OpenAPI schema is the stable public way to enumerate every path.
    # A route registered with include_in_schema=False would not appear here.
    targets: list[tuple[str, str]] = []
    for path, operations in app.openapi()["paths"].items():
        url = re.sub(r"\{[^}]+\}", "1", path)
        targets.extend(
            (verb, url)
            for verb in (method.upper() for method in operations)
            if verb in _HTTP_METHODS and verb not in SAFE_METHODS
        )
    return targets


async def test_every_state_changing_route_rejects_a_hostile_origin(
    client: httpx.AsyncClient,
) -> None:
    targets = _state_changing_routes()

    # Without this the loop passes vacuously if the filter ever stops matching anything.
    assert targets

    for method, path in targets:
        response = await client.request(method, path, headers={"Origin": DISALLOWED})

        assert response.status_code == 403, f"{method} {path} is not origin-guarded"


async def test_a_safe_method_is_exempt_from_the_origin_guard(client: httpx.AsyncClient) -> None:
    response = await client.get("/health", headers={"Origin": DISALLOWED})

    assert response.status_code == 200
