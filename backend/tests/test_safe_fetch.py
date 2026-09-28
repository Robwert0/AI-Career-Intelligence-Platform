import asyncio
import gzip
import socket
import time
from collections.abc import AsyncIterator, Awaitable, Callable

import httpx
import pytest

from app.integrations.errors import FetchError, FetchFailure
from app.integrations.safe_fetch import (
    RobotsCache,
    SafeFetcher,
    is_public_address,
    parse_public_url,
)

PUBLIC = "93.184.216.34"
OTHER_PUBLIC = "151.101.1.69"
PAGE = "<html><body><p>" + "A real job posting. " * 40 + "</p></body></html>"

Handler = Callable[[httpx.Request], httpx.Response | Awaitable[httpx.Response]]


def resolver(mapping: dict[str, list[str]]) -> Callable[[str, int], Awaitable[list[str]]]:
    async def resolve(host: str, port: int) -> list[str]:
        if host not in mapping:
            raise socket.gaierror(socket.EAI_NONAME, "Name or service not known")
        return mapping[host]

    return resolve


def site(
    page: Handler | None = None, *, robots: httpx.Response | None = None
) -> tuple[Handler, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    async def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/robots.txt":
            return robots if robots is not None else httpx.Response(404)
        if page is None:
            return httpx.Response(200, headers={"content-type": "text/html"}, text=PAGE)
        result = page(request)
        if isinstance(result, httpx.Response):
            return result
        return await result

    return handle, seen


def fetcher(
    handler: Handler,
    mapping: dict[str, list[str]] | None = None,
    **kwargs: float,
) -> SafeFetcher:
    return SafeFetcher(
        resolver=resolver(mapping or {"jobs.example.com": [PUBLIC]}),
        # Handler covers both sync and async page functions; MockTransport's overloads
        # only type one shape at a time, though it accepts either at runtime.
        transport=httpx.MockTransport(handler),  # type: ignore[arg-type]
        robots=RobotsCache(),
        **kwargs,
    )


async def failure(coro: Awaitable[object]) -> FetchFailure:
    with pytest.raises(FetchError) as caught:
        await coro
    return caught.value.failure


# --- URL parsing -------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    ["https://jobs.example.com/a?b=1", "http://jobs.example.com", "  https://JOBS.example.com/x  "],
)
def test_public_http_urls_parse(raw: str) -> None:
    url = parse_public_url(raw)

    assert url.host == "jobs.example.com"
    assert url.scheme in ("http", "https")


@pytest.mark.parametrize(
    "raw",
    [
        "ftp://jobs.example.com/",
        "javascript:alert(1)",
        "file:///etc/passwd",
        "https://",
        "https://user:pass@jobs.example.com/",
        "https://jobs.example.com:8443/",
        "http://jobs.example.com:22/",
        "https://[::1",
        "https://jobs.example.com/" + "a" * 2100,
        "https://jobs.example.com/a\x00b",
        "https://jobs.example.com/\x7f",
        "https://jobs.example.com/a b",
        "",
    ],
)
def test_unfetchable_urls_are_invalid(raw: str) -> None:
    with pytest.raises(FetchError) as caught:
        parse_public_url(raw)

    assert caught.value.failure is FetchFailure.INVALID_URL


def test_the_fragment_is_dropped_and_the_query_kept() -> None:
    assert str(parse_public_url("https://jobs.example.com/p?id=7#apply")) == (
        "https://jobs.example.com/p?id=7"
    )


# --- address checks ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("address", "public"),
    [
        (PUBLIC, True),
        ("2606:2800:220:1:248:1893:25c8:1946", True),
        ("127.0.0.1", False),
        ("10.0.0.5", False),
        ("172.16.0.1", False),
        ("192.168.1.1", False),
        ("169.254.169.254", False),
        ("100.64.0.1", False),
        ("0.0.0.0", False),
        ("224.0.0.1", False),
        ("240.0.0.1", False),
        ("::1", False),
        ("fc00::1", False),
        ("fe80::1%eth0", False),
        ("::ffff:10.0.0.1", False),
        ("::ffff:127.0.0.1", False),
        ("64:ff9b::7f00:1", False),
        ("2002:7f00:1::", False),
        ("::7f00:1", False),
        ("::ffff:0:a00:1", False),
        ("::ffff:0:7f00:1", False),
        ("fec0::1", False),
        ("not-an-ip", False),
    ],
)
def test_is_public_address(address: str, public: bool) -> None:
    assert is_public_address(address) is public


# --- pinning and resolution --------------------------------------------------------------


async def test_the_connection_is_pinned_to_the_checked_address() -> None:
    handler, seen = site()

    result = await fetcher(handler).fetch("https://jobs.example.com/careers/42")

    page_request = seen[-1]
    assert page_request.url.host == PUBLIC
    assert page_request.headers["host"] == "jobs.example.com"
    assert page_request.extensions["sni_hostname"] == "jobs.example.com"
    assert result.url == "https://jobs.example.com/careers/42"
    assert "A real job posting." in result.text


async def test_the_user_agent_is_honest() -> None:
    handler, seen = site()

    await fetcher(handler).fetch("https://jobs.example.com/")

    assert seen[-1].headers["user-agent"].startswith("CareerIntelBot/")
    assert "cookie" not in seen[-1].headers
    assert "authorization" not in seen[-1].headers


# --- cookies -------------------------------------------------------------------------------


async def test_a_robots_cookie_is_not_sent_on_the_page_request() -> None:
    robots = httpx.Response(200, headers={"set-cookie": "sid=abc"}, text="")
    handler, seen = site(robots=robots)

    await fetcher(handler).fetch("https://jobs.example.com/")

    assert all("cookie" not in request.headers for request in seen)


async def test_a_redirect_cookie_is_not_sent_on_the_next_hop_or_its_robots() -> None:
    def page(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/old":
            return httpx.Response(301, headers={"location": "/new", "set-cookie": "sid=abc"})
        return httpx.Response(200, headers={"content-type": "text/html"}, text=PAGE)

    handler, seen = site(page)

    await fetcher(handler).fetch("https://jobs.example.com/old")

    assert all("cookie" not in request.headers for request in seen)


async def test_a_private_resolution_is_blocked_before_any_request() -> None:
    handler, seen = site()

    code = await failure(
        fetcher(handler, {"jobs.example.com": ["10.0.0.7"]}).fetch("https://jobs.example.com/")
    )

    assert code is FetchFailure.BLOCKED_ADDRESS
    assert seen == []


async def test_a_mixed_dns_answer_is_blocked_before_any_request() -> None:
    handler, seen = site()

    code = await failure(
        fetcher(handler, {"jobs.example.com": [PUBLIC, "127.0.0.1"]}).fetch(
            "https://jobs.example.com/"
        )
    )

    assert code is FetchFailure.BLOCKED_ADDRESS
    assert seen == []


async def test_an_unknown_host_is_an_invalid_url() -> None:
    handler, _ = site()

    code = await failure(fetcher(handler).fetch("https://nowhere.example.org/"))

    assert code is FetchFailure.INVALID_URL


@pytest.mark.parametrize("host", ["2130706433", "0x7f000001", "017700000001", "127.1"])
async def test_numeric_host_encodings_resolve_to_loopback_and_are_blocked(host: str) -> None:
    handler, seen = site()
    real = SafeFetcher(
        transport=httpx.MockTransport(handler),  # type: ignore[arg-type]
        robots=RobotsCache(),
    )

    code = await failure(real.fetch(f"http://{host}/"))

    # Most resolvers read these as 127.0.0.1 (blocked). One that refuses the spelling instead
    # gives invalid_url. Both are safe; what matters is that nothing was requested.
    assert code in (FetchFailure.BLOCKED_ADDRESS, FetchFailure.INVALID_URL)
    assert seen == []


def test_the_client_ignores_proxy_environment_variables() -> None:
    # A proxy would connect on our behalf and route around the pinned address.
    assert SafeFetcher().build_client().trust_env is False


# --- redirects ---------------------------------------------------------------------------


async def test_a_relative_redirect_is_followed_and_revalidated() -> None:
    def page(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/old":
            return httpx.Response(301, headers={"location": "/new"})
        return httpx.Response(200, headers={"content-type": "text/html"}, text=PAGE)

    handler, seen = site(page)

    result = await fetcher(handler).fetch("https://jobs.example.com/old")

    assert result.url == "https://jobs.example.com/new"


async def test_a_redirect_to_an_internal_host_is_blocked() -> None:
    def page(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "http://metadata.internal/latest"})

    handler, _ = site(page)
    mapping = {"jobs.example.com": [PUBLIC], "metadata.internal": ["169.254.169.254"]}

    code = await failure(fetcher(handler, mapping).fetch("https://jobs.example.com/"))

    assert code is FetchFailure.BLOCKED_ADDRESS


async def test_a_redirect_to_another_scheme_is_invalid() -> None:
    def page(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "file:///etc/passwd"})

    handler, _ = site(page)

    assert await failure(fetcher(handler).fetch("https://jobs.example.com/")) is (
        FetchFailure.INVALID_URL
    )


async def test_a_redirect_with_a_control_character_in_location_is_invalid() -> None:
    def page(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "/x\x00y"})

    handler, _ = site(page)

    assert await failure(fetcher(handler).fetch("https://jobs.example.com/")) is (
        FetchFailure.INVALID_URL
    )


async def test_more_than_three_redirects_are_not_followed() -> None:
    def page(request: httpx.Request) -> httpx.Response:
        hop = int(request.url.path.strip("/") or 0)
        return httpx.Response(302, headers={"location": f"/{hop + 1}"})

    handler, _ = site(page)

    assert await failure(fetcher(handler).fetch("https://jobs.example.com/0")) is (
        FetchFailure.NOT_EXTRACTABLE
    )


# --- status codes, types, sizes ----------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "body", "expected"),
    [
        (401, "", FetchFailure.LOGIN_REQUIRED),
        (403, "", FetchFailure.BLOCKED_BY_SITE),
        (429, "", FetchFailure.BLOCKED_BY_SITE),
        (404, "", FetchFailure.EXPIRED),
        (410, "", FetchFailure.EXPIRED),
        (418, "", FetchFailure.NOT_EXTRACTABLE),
        (500, "", FetchFailure.SITE_UNAVAILABLE),
        (503, "down for maintenance", FetchFailure.SITE_UNAVAILABLE),
        (
            503,
            "<title>Just a moment...</title><div id='cf-chl-widget'>",
            FetchFailure.BLOCKED_BY_SITE,
        ),
    ],
)
async def test_status_codes_map_to_failures(status: int, body: str, expected: FetchFailure) -> None:
    handler, _ = site(lambda request: httpx.Response(status, text=body))

    assert await failure(fetcher(handler).fetch("https://jobs.example.com/")) is expected


@pytest.mark.parametrize("content_type", ["application/pdf", "image/png", "application/json", ""])
async def test_non_text_content_is_not_extractable(content_type: str) -> None:
    handler, _ = site(
        lambda request: httpx.Response(200, headers={"content-type": content_type}, content=b"x")
    )

    assert await failure(fetcher(handler).fetch("https://jobs.example.com/")) is (
        FetchFailure.NOT_EXTRACTABLE
    )


async def test_a_declared_oversize_body_is_too_large() -> None:
    handler, _ = site(
        lambda request: httpx.Response(
            200,
            headers={"content-type": "text/html", "content-length": str(3 * 1024 * 1024)},
            content=b"x",
        )
    )

    assert await failure(fetcher(handler).fetch("https://jobs.example.com/")) is (
        FetchFailure.TOO_LARGE
    )


async def test_an_undeclared_oversize_body_is_too_large() -> None:
    # An async generator body has no Content-Length, so only the streaming cap can stop it.
    async def chunks() -> AsyncIterator[bytes]:
        for _ in range(3):
            yield b"x" * (1024 * 1024)

    handler, _ = site(
        lambda request: httpx.Response(200, headers={"content-type": "text/html"}, content=chunks())
    )

    assert await failure(fetcher(handler).fetch("https://jobs.example.com/")) is (
        FetchFailure.TOO_LARGE
    )


async def test_a_gzip_bomb_is_too_large() -> None:
    bomb = gzip.compress(b"\0" * 20_000_000)
    handler, _ = site(
        lambda request: httpx.Response(
            200, headers={"content-type": "text/html", "content-encoding": "gzip"}, content=bomb
        )
    )

    assert await failure(fetcher(handler).fetch("https://jobs.example.com/")) is (
        FetchFailure.TOO_LARGE
    )


async def test_a_small_gzip_body_is_decoded() -> None:
    handler, _ = site(
        lambda request: httpx.Response(
            200,
            headers={"content-type": "text/html", "content-encoding": "gzip"},
            content=gzip.compress(PAGE.encode()),
        )
    )

    result = await fetcher(handler).fetch("https://jobs.example.com/")

    assert "A real job posting." in result.text


async def test_an_unsupported_encoding_is_not_extractable() -> None:
    handler, _ = site(
        lambda request: httpx.Response(
            200, headers={"content-type": "text/html", "content-encoding": "br"}, content=b"x"
        )
    )

    assert await failure(fetcher(handler).fetch("https://jobs.example.com/")) is (
        FetchFailure.NOT_EXTRACTABLE
    )


async def test_the_declared_charset_is_honoured() -> None:
    handler, _ = site(
        lambda request: httpx.Response(
            200,
            headers={"content-type": "text/html; charset=iso-8859-1"},
            content="Développeur".encode("iso-8859-1"),
        )
    )

    result = await fetcher(handler).fetch("https://jobs.example.com/")

    assert result.text == "Développeur"


def charset_page(charset: str, body: bytes) -> Handler:
    handler, _ = site(
        lambda request: httpx.Response(
            200, headers={"content-type": f"text/plain; charset={charset}"}, content=body
        )
    )
    return handler


async def test_a_punycode_charset_is_decoded_as_utf8_without_the_quadratic_decoder() -> None:
    n = 160 * 1024
    body = b"a" * n + b"-" + b"z" * n

    started = time.perf_counter()
    result = await fetcher(charset_page("punycode", body)).fetch("https://jobs.example.com/")
    elapsed = time.perf_counter() - started

    assert elapsed < 0.5
    assert result.text == body.decode("utf-8")


@pytest.mark.parametrize(
    "charset",
    ["rot13", "base64", "zlib", "hex", "uu", "idna", "unicode_escape", "raw_unicode_escape"],
)
async def test_a_non_text_charset_falls_back_to_utf8(charset: str) -> None:
    body = "Développeur \\u0041 cafe".encode()

    result = await fetcher(charset_page(charset, body)).fetch("https://jobs.example.com/")

    assert result.text == body.decode("utf-8")


@pytest.mark.parametrize(
    ("charset", "text"),
    [("latin-1", "Développeur"), ("windows-1252", "Café €"), ("shift_jis", "開発者")],
)
async def test_real_text_charsets_are_still_honoured(charset: str, text: str) -> None:
    result = await fetcher(charset_page(charset, text.encode(charset))).fetch(
        "https://jobs.example.com/"
    )

    assert result.text == text


async def test_a_slow_site_times_out() -> None:
    async def slow(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(2)
        return httpx.Response(200, headers={"content-type": "text/html"}, text=PAGE)

    handler, _ = site(slow)

    code = await failure(fetcher(handler, total_timeout=0.2).fetch("https://jobs.example.com/"))

    assert code is FetchFailure.FETCH_TIMEOUT


async def test_a_connection_failure_is_site_unavailable() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    handler, _ = site(refuse)

    assert await failure(fetcher(handler).fetch("https://jobs.example.com/")) is (
        FetchFailure.SITE_UNAVAILABLE
    )


async def test_a_broken_server_response_is_site_unavailable() -> None:
    def page(request: httpx.Request) -> httpx.Response:
        raise httpx.RemoteProtocolError("Server disconnected without sending a response.")

    handler, _ = site(page)

    assert await failure(fetcher(handler).fetch("https://jobs.example.com/")) is (
        FetchFailure.SITE_UNAVAILABLE
    )


async def test_a_broken_robots_response_is_site_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.RemoteProtocolError("Server disconnected without sending a response.")

    assert await failure(fetcher(handler).fetch("https://jobs.example.com/")) is (
        FetchFailure.SITE_UNAVAILABLE
    )


# --- robots.txt --------------------------------------------------------------------------


async def test_a_robots_disallow_for_our_agent_blocks_without_fetching_the_page() -> None:
    robots = httpx.Response(200, text="User-agent: CareerIntelBot\nDisallow: /jobs/\n")
    handler, seen = site(robots=robots)

    code = await failure(fetcher(handler).fetch("https://jobs.example.com/jobs/1"))

    assert code is FetchFailure.BLOCKED_BY_ROBOTS
    assert [request.url.path for request in seen] == ["/robots.txt"]


async def test_a_wildcard_disallow_blocks_us_too() -> None:
    handler, _ = site(robots=httpx.Response(200, text="User-agent: *\nDisallow: /\n"))

    assert await failure(fetcher(handler).fetch("https://jobs.example.com/x")) is (
        FetchFailure.BLOCKED_BY_ROBOTS
    )


async def test_a_disallow_for_another_bot_does_not_block_us() -> None:
    handler, _ = site(robots=httpx.Response(200, text="User-agent: BadBot\nDisallow: /\n"))

    result = await fetcher(handler).fetch("https://jobs.example.com/x")

    assert "A real job posting." in result.text


async def test_a_missing_robots_file_allows_everything() -> None:
    handler, _ = site(robots=httpx.Response(404))

    assert (await fetcher(handler).fetch("https://jobs.example.com/x")).text


async def test_an_erroring_robots_file_means_disallow_all() -> None:
    # RFC 9309: an unreachable robots.txt means the crawler must assume complete disallow.
    handler, _ = site(robots=httpx.Response(503))

    assert await failure(fetcher(handler).fetch("https://jobs.example.com/x")) is (
        FetchFailure.BLOCKED_BY_ROBOTS
    )


async def test_robots_rules_are_cached_per_origin() -> None:
    handler, seen = site()
    shared = fetcher(handler)

    await shared.fetch("https://jobs.example.com/a")
    await shared.fetch("https://jobs.example.com/b")

    assert [request.url.path for request in seen].count("/robots.txt") == 1


async def test_a_transient_robots_failure_is_not_cached() -> None:
    handler, seen = site(robots=httpx.Response(503))
    shared = fetcher(handler)

    await failure(shared.fetch("https://jobs.example.com/a"))
    await failure(shared.fetch("https://jobs.example.com/b"))

    assert [request.url.path for request in seen].count("/robots.txt") == 2


async def test_a_robots_connection_failure_is_site_unavailable() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    assert await failure(fetcher(refuse).fetch("https://jobs.example.com/")) is (
        FetchFailure.SITE_UNAVAILABLE
    )


async def test_a_slow_robots_file_times_out() -> None:
    async def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            await asyncio.sleep(2)
        return httpx.Response(200, headers={"content-type": "text/html"}, text=PAGE)

    code = await failure(fetcher(handle, robots_timeout=0.2).fetch("https://jobs.example.com/"))

    assert code is FetchFailure.FETCH_TIMEOUT


async def test_a_redirect_to_another_host_checks_that_hosts_robots() -> None:
    async def handle(request: httpx.Request) -> httpx.Response:
        host = request.headers["host"]
        if request.url.path == "/robots.txt":
            body = "User-agent: *\nDisallow: /\n" if host == "ats.example.net" else ""
            return httpx.Response(200, text=body)
        return httpx.Response(302, headers={"location": "https://ats.example.net/job/9"})

    mapping = {"jobs.example.com": [PUBLIC], "ats.example.net": [OTHER_PUBLIC]}

    code = await failure(fetcher(handle, mapping).fetch("https://jobs.example.com/apply"))

    assert code is FetchFailure.BLOCKED_BY_ROBOTS
