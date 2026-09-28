import asyncio
import json
import time
import uuid
from collections.abc import AsyncGenerator, Callable
from typing import Any

import httpx
import pytest
import pytest_asyncio
from redis.asyncio import Redis

from app.core.redis import create_redis
from app.integrations.errors import GitHubError, GitHubFailure
from app.integrations.github import (
    MAX_README_BYTES,
    MAX_REPOS,
    GitHubCache,
    GitHubClient,
    GitHubProfile,
    GitHubSnapshot,
    load_github,
    parse_github_profile_url,
)

USER = "octo-dev"


def repo(name: str, **overrides: Any) -> dict[str, Any]:
    return {
        "name": name,
        "description": f"{name} description",
        "language": "Go",
        "topics": ["payments"],
        "stargazers_count": 3,
        "pushed_at": "2026-09-01T10:00:00Z",
        "fork": False,
        "archived": False,
        "disabled": False,
        "private": False,
    } | overrides


def profile(**overrides: Any) -> dict[str, Any]:
    return {
        "login": USER,
        "name": "Octo Dev",
        "bio": "Backend engineer",
        "company": "Acme",
        "blog": "",
        "public_repos": 4,
        "email": "octo@example.com",
    } | overrides


Route = Callable[[httpx.Request], httpx.Response]


class Api:
    """A fake api.github.com; `routes` overrides any path ending in its key."""

    def __init__(
        self,
        *,
        repos: list[dict[str, Any]] | None = None,
        routes: dict[str, Route] | None = None,
    ) -> None:
        self.repos = repos if repos is not None else [repo("ledger"), repo("jarvis")]
        self.routes = routes or {}
        self.seen: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.seen.append(request)
        path = request.url.path
        for suffix, route in self.routes.items():
            if path.endswith(suffix):
                return route(request)
        if path == f"/users/{USER}":
            return httpx.Response(200, json=profile())
        if path == f"/users/{USER}/repos":
            return httpx.Response(200, json=self.repos)
        if path.endswith("/languages"):
            return httpx.Response(200, json={"Go": 7000, "Shell": 3000})
        if path.endswith("/readme"):
            name = path.split("/")[3]
            return httpx.Response(200, text=f"# {name}\nA ledger service in Go.")
        return httpx.Response(404, json={"message": "Not Found"})

    def paths(self) -> list[str]:
        return [request.url.path for request in self.seen]


def client(api: Api, *, token: str | None = None, **kwargs: float) -> GitHubClient:
    return GitHubClient(token=token, transport=httpx.MockTransport(api), **kwargs)


async def failure_of(api: Api) -> GitHubError:
    with pytest.raises(GitHubError) as caught:
        await client(api).fetch(USER)
    return caught.value


@pytest.mark.parametrize(
    ("raw", "username"),
    [
        ("https://github.com/octo-dev", "octo-dev"),
        ("https://github.com/octo-dev/", "octo-dev"),
        ("  https://GitHub.com/Octo-Dev  ", "Octo-Dev"),
        ("https://github.com/a", "a"),
    ],
)
def test_a_profile_url_yields_its_username(raw: str, username: str) -> None:
    assert parse_github_profile_url(raw) == username


@pytest.mark.parametrize(
    "raw",
    [
        "http://github.com/octo-dev",
        "https://gitlab.com/octo-dev",
        "https://github.com.evil.example/octo-dev",
        "https://user@github.com/octo-dev",
        "https://github.com:8443/octo-dev",
        "https://github.com/octo-dev/ledger",
        "https://github.com/octo-dev//",
        "https://github.com/octo-dev?tab=repositories",
        "https://github.com/octo-dev#top",
        "https://github.com/-octo",
        "https://github.com/octo-",
        "https://github.com/" + "a" * 40,
        "https://github.com/../../admin",
        "https://github.com/",
        "github.com/octo-dev",
        "",
    ],
)
def test_anything_but_a_profile_url_is_invalid(raw: str) -> None:
    with pytest.raises(GitHubError) as caught:
        parse_github_profile_url(raw)

    assert caught.value.failure is GitHubFailure.INVALID_GITHUB_URL


async def test_a_profile_becomes_a_snapshot_of_its_repositories() -> None:
    api = Api()

    snapshot = await client(api).fetch(USER)

    assert snapshot.profile.login == USER
    assert snapshot.profile.bio == "Backend engineer"
    assert [r.name for r in snapshot.repos] == ["ledger", "jarvis"]
    ledger = snapshot.repos[0]
    assert ledger.url == f"https://github.com/{USER}/ledger"
    assert ledger.languages == {"Go": 7000, "Shell": 3000}
    assert ledger.topics == ["payments"]
    assert ledger.readme is not None and "ledger service" in ledger.readme
    assert (snapshot.candidate_repos, snapshot.readmes_found) == (2, 2)


async def test_the_profile_email_is_never_kept() -> None:
    snapshot = await client(Api()).fetch(USER)

    assert "octo@example.com" not in snapshot.model_dump_json()


async def test_the_repositories_are_listed_most_recently_pushed_first() -> None:
    api = Api()

    await client(api).fetch(USER)

    listing = next(r for r in api.seen if r.url.path == f"/users/{USER}/repos")
    assert listing.url.params["sort"] == "pushed"
    assert listing.url.params["per_page"] == "30"


async def test_forks_and_archived_repositories_are_skipped() -> None:
    api = Api(repos=[repo("mine"), repo("forked", fork=True), repo("old", archived=True)])

    snapshot = await client(api).fetch(USER)

    assert [r.name for r in snapshot.repos] == ["mine"]
    assert snapshot.candidate_repos == 1
    assert not any("forked" in path or "/old/" in path for path in api.paths())


async def test_at_most_ten_repositories_are_inspected() -> None:
    api = Api(repos=[repo(f"repo{n}") for n in range(25)])

    snapshot = await client(api).fetch(USER)

    assert len(snapshot.repos) == MAX_REPOS
    assert snapshot.candidate_repos == 25
    assert sum(path.endswith("/readme") for path in api.paths()) == MAX_REPOS


async def test_a_repository_without_a_readme_is_kept_without_one() -> None:
    api = Api(
        repos=[repo("bare")],
        routes={"/readme": lambda _: httpx.Response(404, json={"message": "Not Found"})},
    )

    snapshot = await client(api).fetch(USER)

    assert snapshot.repos[0].readme is None
    assert snapshot.readmes_found == 0


async def test_a_readme_is_cut_at_eight_kilobytes() -> None:
    api = Api(
        repos=[repo("big")], routes={"/readme": lambda _: httpx.Response(200, text="x" * 100_000)}
    )

    snapshot = await client(api).fetch(USER)

    readme = snapshot.repos[0].readme
    assert readme is not None and len(readme) == MAX_README_BYTES


async def test_a_repository_with_an_unsafe_name_is_never_requested() -> None:
    api = Api(repos=[repo("../../orgs/acme"), repo("ok")])

    snapshot = await client(api).fetch(USER)

    assert [r.name for r in snapshot.repos] == ["ok"]
    assert all("orgs" not in path for path in api.paths())


async def test_every_request_goes_to_the_github_api_with_an_honest_user_agent() -> None:
    api = Api()

    await client(api).fetch(USER)

    assert {request.url.host for request in api.seen} == {"api.github.com"}
    assert all("CareerIntelBot" in request.headers["user-agent"] for request in api.seen)
    assert all("authorization" not in request.headers for request in api.seen)


async def test_a_token_is_sent_as_a_bearer_header() -> None:
    api = Api()

    await client(api, token="ghp_test").fetch(USER)

    assert {request.headers["authorization"] for request in api.seen} == {"Bearer ghp_test"}


def test_the_client_ignores_proxy_environment_variables() -> None:
    assert GitHubClient().build_client().trust_env is False


async def test_an_unknown_user_is_not_found() -> None:
    api = Api(routes={f"/users/{USER}": lambda _: httpx.Response(404, json={})})

    assert (await failure_of(api)).failure is GitHubFailure.GITHUB_USER_NOT_FOUND


async def test_an_exhausted_rate_limit_reports_its_reset_time() -> None:
    limited = httpx.Response(
        403, headers={"x-ratelimit-remaining": "0", "x-ratelimit-reset": "1790000000"}, json={}
    )
    api = Api(routes={f"/users/{USER}": lambda _: limited})

    error = await failure_of(api)

    assert error.failure is GitHubFailure.GITHUB_RATE_LIMITED
    assert error.reset_at == 1790000000


async def test_a_secondary_rate_limit_uses_retry_after() -> None:
    api = Api(
        routes={f"/users/{USER}": lambda _: httpx.Response(429, headers={"retry-after": "60"})}
    )

    error = await failure_of(api)

    assert error.failure is GitHubFailure.GITHUB_RATE_LIMITED
    assert error.reset_at is not None
    assert 0 < error.reset_at - time.time() <= 61


async def test_a_rate_limit_hit_midway_fails_the_whole_snapshot() -> None:
    limited = httpx.Response(403, headers={"x-ratelimit-remaining": "0"}, json={})
    api = Api(routes={"/readme": lambda _: limited})

    assert (await failure_of(api)).failure is GitHubFailure.GITHUB_RATE_LIMITED


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(500),
        httpx.Response(502),
        httpx.Response(403, json={"message": "Forbidden"}),
        httpx.Response(301, headers={"location": "https://api.github.com/users/other"}),
        httpx.Response(200, text="<html>not json</html>"),
        httpx.Response(200, json={"unexpected": True}),
    ],
    ids=["500", "502", "plain-403", "redirect", "not-json", "wrong-shape"],
)
async def test_other_responses_are_unavailable(response: httpx.Response) -> None:
    api = Api(routes={f"/users/{USER}": lambda _: response})

    assert (await failure_of(api)).failure is GitHubFailure.GITHUB_UNAVAILABLE


async def test_a_profile_for_a_different_login_is_unavailable() -> None:
    api = Api(routes={f"/users/{USER}": lambda _: httpx.Response(200, json=profile(login="other"))})

    assert (await failure_of(api)).failure is GitHubFailure.GITHUB_UNAVAILABLE


async def test_an_oversized_listing_is_unavailable() -> None:
    api = Api(repos=[repo(f"r{n}", description="x" * 300) for n in range(3000)])

    assert (await failure_of(api)).failure is GitHubFailure.GITHUB_UNAVAILABLE


async def test_a_connection_error_is_unavailable() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    api = Api(routes={f"/users/{USER}": refuse})

    error = await failure_of(api)

    assert error.failure is GitHubFailure.GITHUB_UNAVAILABLE
    assert error.__suppress_context__ is True


async def test_a_slow_api_is_cut_off_at_the_total_timeout() -> None:
    async def slow(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(5)
        return httpx.Response(200, json=profile())

    started = time.monotonic()
    with pytest.raises(GitHubError) as caught:
        await GitHubClient(transport=httpx.MockTransport(slow), total_timeout=0.2).fetch(USER)

    assert caught.value.failure is GitHubFailure.GITHUB_UNAVAILABLE
    assert time.monotonic() - started < 2


@pytest_asyncio.fixture
async def redis_client() -> AsyncGenerator[Redis]:
    redis = create_redis()
    yield redis
    await redis.aclose()


class CountingFetcher:
    def __init__(self, error: GitHubError | None = None) -> None:
        self.calls: list[str] = []
        self.error = error

    async def fetch(self, username: str) -> GitHubSnapshot:
        self.calls.append(username)
        if self.error is not None:
            raise self.error
        return GitHubSnapshot(
            profile=GitHubProfile(login=username, public_repos=0),
            repos=[],
            candidate_repos=0,
            fetched_at=time.time(),
        )


def unique_user() -> str:
    return f"u{uuid.uuid4().hex[:12]}"


async def test_a_second_load_within_the_hour_comes_from_the_cache(redis_client: Redis) -> None:
    fetcher, cache, user = (
        CountingFetcher(),
        GitHubCache(redis_client, ttl_seconds=3600),
        unique_user(),
    )

    first = await load_github(user, fetcher=fetcher, cache=cache)
    second = await load_github(user, fetcher=fetcher, cache=cache)

    assert fetcher.calls == [user]
    assert second == first
    assert 0 < await redis_client.ttl(f"match:gh:{user}") <= 3600


async def test_the_cache_key_ignores_username_case(redis_client: Redis) -> None:
    fetcher, cache, user = (
        CountingFetcher(),
        GitHubCache(redis_client, ttl_seconds=60),
        unique_user(),
    )

    await load_github(user, fetcher=fetcher, cache=cache)
    await load_github(user.upper(), fetcher=fetcher, cache=cache)

    assert fetcher.calls == [user]


async def test_a_failure_is_never_cached(redis_client: Redis) -> None:
    error = GitHubError(GitHubFailure.GITHUB_RATE_LIMITED, reset_at=1)
    fetcher, cache, user = (
        CountingFetcher(error),
        GitHubCache(redis_client, ttl_seconds=60),
        unique_user(),
    )

    for _ in range(2):
        with pytest.raises(GitHubError):
            await load_github(user, fetcher=fetcher, cache=cache)

    assert fetcher.calls == [user, user]
    assert await redis_client.exists(f"match:gh:{user}") == 0


async def test_a_corrupt_cache_entry_is_refetched(
    redis_client: Redis, caplog: pytest.LogCaptureFixture
) -> None:
    fetcher, cache, user = (
        CountingFetcher(),
        GitHubCache(redis_client, ttl_seconds=60),
        unique_user(),
    )
    await redis_client.set(f"match:gh:{user}", json.dumps({"not": "a snapshot"}), ex=60)

    with caplog.at_level("WARNING"):
        snapshot = await load_github(user, fetcher=fetcher, cache=cache)

    assert snapshot.profile.login == user
    assert fetcher.calls == [user]
    assert "github cache entry corrupt" in caplog.text
    assert "ValidationError" in caplog.text


async def test_a_github_unavailable_mapping_is_logged_by_type(
    caplog: pytest.LogCaptureFixture,
) -> None:
    api = Api(routes={f"/users/{USER}": lambda _: httpx.Response(200, text="not json")})

    with caplog.at_level("WARNING"):
        error = await failure_of(api)

    assert error.failure is GitHubFailure.GITHUB_UNAVAILABLE
    assert "github_unavailable" in caplog.text
    assert "JSONDecodeError" in caplog.text


async def test_an_unreachable_cache_still_loads(caplog: pytest.LogCaptureFixture) -> None:
    dead = Redis.from_url("redis://127.0.0.1:1/0", socket_connect_timeout=0.2)
    fetcher = CountingFetcher()
    try:
        with caplog.at_level("WARNING"):
            await load_github("octo", fetcher=fetcher, cache=GitHubCache(dead, ttl_seconds=60))
    finally:
        await dead.aclose()

    assert fetcher.calls == ["octo"]
    assert "github cache read failed" in caplog.text
