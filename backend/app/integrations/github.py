import asyncio
import json
import logging
import re
import time
from typing import Annotated, Any, Protocol
from urllib.parse import quote, urlsplit

import httpx
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, TypeAdapter, ValidationError
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.integrations.errors import FetchError, GitHubError, GitHubFailure
from app.integrations.safe_fetch import hardened_client, read_bounded

logger = logging.getLogger(__name__)

API_BASE = "https://api.github.com"
MAX_REPOS = 10
REPO_PAGE_SIZE = 30
MAX_JSON_BYTES = 1024 * 1024
MAX_README_BYTES = 8 * 1024
TOTAL_TIMEOUT_SECONDS = 20.0
_CONCURRENCY = 4
_USERNAME = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?")
_REPO_NAME = re.compile(r"[A-Za-z0-9._-]{1,100}")
_LANGUAGES = TypeAdapter(dict[str, int])


def _clip(limit: int) -> BeforeValidator:
    return BeforeValidator(lambda value: value[:limit] if isinstance(value, str) else value)


class GitHubProfile(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    login: str
    name: Annotated[str | None, _clip(100)] = None
    bio: Annotated[str | None, _clip(300)] = None
    company: Annotated[str | None, _clip(100)] = None
    blog: Annotated[str | None, _clip(200)] = None
    public_repos: int = Field(default=0, ge=0)


class _ApiRepo(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    description: Annotated[str | None, _clip(300)] = None
    language: str | None = None
    topics: list[str] = Field(default_factory=list)
    stargazers_count: int = 0
    pushed_at: str | None = None
    fork: bool
    archived: bool = False
    disabled: bool = False


class GitHubRepo(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    url: str
    description: str | None
    languages: dict[str, int]
    topics: list[str]
    stars: int
    pushed_at: str | None
    readme: str | None


class GitHubSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    profile: GitHubProfile
    repos: list[GitHubRepo]
    candidate_repos: int
    fetched_at: float

    @property
    def readmes_found(self) -> int:
        return sum(1 for repo in self.repos if repo.readme)


def parse_github_profile_url(raw: str) -> str:
    raw = raw.strip()
    try:
        parts = urlsplit(raw)
        port = parts.port
    except ValueError:
        raise GitHubError(GitHubFailure.INVALID_GITHUB_URL) from None
    username = parts.path.removesuffix("/").removeprefix("/")
    if (
        len(raw) > 100
        or parts.scheme != "https"
        or parts.netloc.lower() != "github.com"
        or port is not None
        or parts.query
        or parts.fragment
        or not _USERNAME.fullmatch(username)
    ):
        raise GitHubError(GitHubFailure.INVALID_GITHUB_URL)
    return username


def _rate_limited(response: httpx.Response) -> GitHubError:
    reset = response.headers.get("x-ratelimit-reset", "")
    retry_after = response.headers.get("retry-after", "")
    if reset.isdigit():
        reset_at: int | None = int(reset)
    elif retry_after.isdigit():
        reset_at = int(time.time()) + int(retry_after)
    else:
        reset_at = None
    return GitHubError(GitHubFailure.GITHUB_RATE_LIMITED, reset_at=reset_at)


def _is_rate_limit(response: httpx.Response) -> bool:
    return response.status_code == 429 or (
        response.status_code == 403
        and (
            response.headers.get("x-ratelimit-remaining") == "0"
            or "retry-after" in response.headers
        )
    )


class GitHubClient:
    def __init__(
        self,
        *,
        token: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        total_timeout: float = TOTAL_TIMEOUT_SECONDS,
    ) -> None:
        self._token = token
        self._transport = transport
        self._total_timeout = total_timeout

    def build_client(self) -> httpx.AsyncClient:
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return hardened_client(transport=self._transport, headers=headers, base_url=API_BASE)

    async def fetch(self, username: str) -> GitHubSnapshot:
        if not _USERNAME.fullmatch(username):
            raise GitHubError(GitHubFailure.INVALID_GITHUB_URL)
        async with self.build_client() as client:
            try:
                async with asyncio.timeout(self._total_timeout):
                    return await self._snapshot(client, username)
            except (TimeoutError, httpx.HTTPError, FetchError) as exc:
                logger.warning("github_unavailable error_type=%s", type(exc).__name__)
                raise GitHubError(GitHubFailure.GITHUB_UNAVAILABLE) from None

    async def _get(
        self,
        client: httpx.AsyncClient,
        path: str,
        *,
        params: dict[str, str | int] | None = None,
        raw: bool = False,
    ) -> bytes | None:
        headers = {"Accept": "application/vnd.github.raw+json"} if raw else {}
        request = client.build_request("GET", path, params=params, headers=headers)
        response = await client.send(request, stream=True)
        try:
            if response.status_code == 404:
                return None
            if _is_rate_limit(response):
                raise _rate_limited(response)
            if response.status_code != 200:
                logger.warning("github_unavailable status=%s", response.status_code)
                raise GitHubError(GitHubFailure.GITHUB_UNAVAILABLE)
            if raw:
                return await read_bounded(response, MAX_README_BYTES, truncate=True)
            return await read_bounded(response, MAX_JSON_BYTES, truncate=False)
        finally:
            await response.aclose()

    async def _json(self, client: httpx.AsyncClient, path: str, **kwargs: Any) -> Any | None:
        body = await self._get(client, path, **kwargs)
        if body is None:
            return None
        try:
            return json.loads(body)
        except ValueError as exc:
            logger.warning("github_unavailable error_type=%s", type(exc).__name__)
            raise GitHubError(GitHubFailure.GITHUB_UNAVAILABLE) from None

    async def _snapshot(self, client: httpx.AsyncClient, username: str) -> GitHubSnapshot:
        user = await self._json(client, f"/users/{username}")
        if user is None:
            raise GitHubError(GitHubFailure.GITHUB_USER_NOT_FOUND)
        listing = await self._json(
            client,
            f"/users/{username}/repos",
            params={"sort": "pushed", "per_page": REPO_PAGE_SIZE, "type": "owner"},
        )
        try:
            profile = GitHubProfile.model_validate(user)
            listed = [_ApiRepo.model_validate(item) for item in listing or []]
        except ValidationError as exc:
            logger.warning("github_unavailable error_type=%s", type(exc).__name__)
            raise GitHubError(GitHubFailure.GITHUB_UNAVAILABLE) from None
        if profile.login.lower() != username.lower():
            logger.warning("github_unavailable reason=login_mismatch")
            raise GitHubError(GitHubFailure.GITHUB_UNAVAILABLE)

        candidates = [
            repo
            for repo in listed
            if not (repo.fork or repo.archived or repo.disabled)
            and _REPO_NAME.fullmatch(repo.name)
            and repo.name not in (".", "..")
        ]
        limit = asyncio.Semaphore(_CONCURRENCY)
        ordered = candidates[:MAX_REPOS]
        results: list[GitHubRepo | None] = [None] * len(ordered)

        async def detail(index: int, repo: _ApiRepo) -> None:
            async with limit:
                results[index] = await self._repo(client, profile.login, repo)

        try:
            # TaskGroup, not gather: one repo failing cancels its still-running siblings
            # instead of leaving them to finish in the background for nothing.
            async with asyncio.TaskGroup() as tg:
                for index, repo in enumerate(ordered):
                    tg.create_task(detail(index, repo))
        except ExceptionGroup as eg:
            raise eg.exceptions[0] from None
        repos = [repo for repo in results if repo is not None]
        return GitHubSnapshot(
            profile=profile,
            repos=repos,
            candidate_repos=len(candidates),
            fetched_at=time.time(),
        )

    async def _repo(self, client: httpx.AsyncClient, login: str, repo: _ApiRepo) -> GitHubRepo:
        base = f"/repos/{quote(login, safe='')}/{quote(repo.name, safe='')}"
        languages = await self._json(client, f"{base}/languages")
        readme = await self._get(client, f"{base}/readme", raw=True)
        try:
            parsed_languages = _LANGUAGES.validate_python(languages or {})
        except ValidationError as exc:
            logger.warning("github_unavailable error_type=%s", type(exc).__name__)
            raise GitHubError(GitHubFailure.GITHUB_UNAVAILABLE) from None
        return GitHubRepo(
            name=repo.name,
            url=f"https://github.com/{login}/{repo.name}",
            description=repo.description,
            languages=parsed_languages,
            topics=[topic[:50] for topic in repo.topics[:20]],
            stars=repo.stargazers_count,
            pushed_at=repo.pushed_at,
            readme=readme.decode("utf-8", errors="replace") if readme else None,
        )


class GitHubFetcher(Protocol):
    async def fetch(self, username: str) -> GitHubSnapshot: ...


class GitHubCache:
    def __init__(self, redis: Redis, *, ttl_seconds: int) -> None:
        self._redis = redis
        self._ttl = ttl_seconds

    @staticmethod
    def _key(username: str) -> str:
        # GitHub logins are case-insensitive: one entry per account, however it was typed.
        return f"match:gh:{username.lower()}"

    async def get(self, username: str) -> GitHubSnapshot | None:
        try:
            raw = await self._redis.get(self._key(username))
        except RedisError as exc:
            logger.warning("github cache read failed error_type=%s", type(exc).__name__)
            return None
        if raw is None:
            return None
        try:
            return GitHubSnapshot.model_validate_json(raw)
        except ValidationError as exc:
            logger.warning("github cache entry corrupt error_type=%s", type(exc).__name__)
            return None

    async def put(self, username: str, snapshot: GitHubSnapshot) -> None:
        try:
            await self._redis.set(self._key(username), snapshot.model_dump_json(), ex=self._ttl)
        except RedisError as exc:
            logger.warning("github cache write failed error_type=%s", type(exc).__name__)


async def load_github(
    username: str, *, fetcher: GitHubFetcher, cache: GitHubCache
) -> GitHubSnapshot:
    cached = await cache.get(username)
    if cached is not None:
        return cached
    snapshot = await fetcher.fetch(username)
    await cache.put(username, snapshot)
    return snapshot
