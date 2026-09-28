import asyncio
import codecs
import http.cookiejar
import ipaddress
import socket
import time
import zlib
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx

from app.integrations.errors import FetchError, FetchFailure
from app.integrations.html_text import looks_like_challenge

Resolver = Callable[[str, int], Awaitable[list[str]]]

USER_AGENT_TOKEN = "CareerIntelBot"
USER_AGENT = (
    f"{USER_AGENT_TOKEN}/0.1 (+https://github.com/Robwert0/AI-Career-Intelligence-Platform)"
)
MAX_URL_CHARS = 2048
MAX_BODY_BYTES = 2 * 1024 * 1024
MAX_ROBOTS_BYTES = 512 * 1024
MAX_PEEK_BYTES = 64 * 1024
MAX_REDIRECTS = 3
TEXT_TYPES = frozenset({"text/html", "text/plain"})
_PORTS = {"http": 80, "https": 443}
_TIMEOUT = httpx.Timeout(connect=3.0, read=5.0, write=5.0, pool=3.0)
# IPv6 ranges "global" alone doesn't make reachable-safe: most carry an IPv4 address inside
# them (translation/mapping schemes), and fec0::/10 is deprecated site-local space that
# ipaddress does not classify as private.
_UNSAFE_V6 = tuple(
    ipaddress.ip_network(network)
    for network in (
        "::/96",
        "64:ff9b::/96",
        "64:ff9b:1::/48",
        "2002::/16",
        "2001::/32",
        "::ffff:0:0:0/96",
        "fec0::/10",
    )
)
_ALLOW_ALL: list[str] = []
_DISALLOW_ALL = ["User-agent: *", "Disallow: /"]
# httpx 0.28 _client.py:526 (_redirect_url) raises RemoteProtocolError with this exact prefix
# for a malformed Location header; any other RemoteProtocolError is a genuine broken-server
# wire-protocol failure (disconnect, bad status line, ...), not a URL problem.
_INVALID_LOCATION_PREFIX = "Invalid URL in location header"


@dataclass(frozen=True, slots=True)
class PublicUrl:
    scheme: str
    host: str
    target: str

    @property
    def netloc(self) -> str:
        return _netloc(self.host)

    @property
    def origin(self) -> str:
        return f"{self.scheme}://{self.netloc}"

    def __str__(self) -> str:
        return f"{self.origin}{self.target}"


@dataclass(frozen=True, slots=True)
class FetchResult:
    url: str
    content_type: str
    text: str


def _netloc(host: str) -> str:
    return f"[{host}]" if ":" in host else host


def parse_public_url(raw: str) -> PublicUrl:
    raw = raw.strip()
    if not raw or len(raw) > MAX_URL_CHARS:
        raise FetchError(FetchFailure.INVALID_URL)
    # Control characters (incl. space) can smuggle a header/line break past a lenient parser
    # further down the line; JSON input can carry a literal "\u0000" straight into this string.
    if any(ord(char) < 0x21 or ord(char) == 0x7F for char in raw):
        raise FetchError(FetchFailure.INVALID_URL)
    try:
        parts = urlsplit(raw)
        port = parts.port
    except ValueError:
        raise FetchError(FetchFailure.INVALID_URL) from None
    scheme = parts.scheme.lower()
    hostname = parts.hostname
    if (
        scheme not in _PORTS
        or not hostname
        or parts.username is not None
        or parts.password is not None
        or (port is not None and port != _PORTS[scheme])
    ):
        raise FetchError(FetchFailure.INVALID_URL)
    try:
        host = hostname if ":" in hostname else hostname.encode("idna").decode("ascii")
    except UnicodeError:
        raise FetchError(FetchFailure.INVALID_URL) from None
    if len(host) > 253:
        raise FetchError(FetchFailure.INVALID_URL)
    target = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
    return PublicUrl(scheme, host.lower(), target)


def is_public_address(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address.split("%", 1)[0])
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped is not None:
            return is_public_address(str(ip.ipv4_mapped))
        if any(ip in network for network in _UNSAFE_V6):
            return False
    return ip.is_global and not ip.is_multicast


async def system_resolver(host: str, port: int) -> list[str]:
    infos = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return [str(info[4][0]) for info in infos]


class RobotsCache:
    def __init__(self, *, ttl_seconds: float = 3600.0, max_hosts: int = 256) -> None:
        self._ttl = ttl_seconds
        self._max_hosts = max_hosts
        self._entries: dict[str, tuple[float, RobotFileParser]] = {}

    def get(self, origin: str, now: float) -> RobotFileParser | None:
        entry = self._entries.get(origin)
        if entry is None or entry[0] <= now:
            return None
        return entry[1]

    def put(self, origin: str, parser: RobotFileParser, now: float) -> None:
        if origin not in self._entries and len(self._entries) >= self._max_hosts:
            oldest = min(self._entries, key=lambda key: self._entries[key][0])
            del self._entries[oldest]
        self._entries[origin] = (now + self._ttl, parser)


_SHARED_ROBOTS = RobotsCache()


def _rules(lines: list[str]) -> RobotFileParser:
    parser = RobotFileParser()
    parser.parse(lines)
    return parser


def _decode(body: bytes, response: httpx.Response) -> str:
    charset = response.charset_encoding or "utf-8"
    try:
        codecs.lookup(charset)
    except LookupError:
        charset = "utf-8"
    return body.decode(charset, errors="replace")


async def _iter_raw(response: httpx.Response) -> AsyncIterator[bytes]:
    # response.aiter_raw() refuses a body httpx already buffered at construction time
    # (a MockTransport handler built from bytes/text, not a real network body), and
    # response.content there is decoded, not raw. The stream itself still holds the
    # untouched wire bytes either way, so read from it directly.
    stream = response.stream
    assert isinstance(stream, httpx.AsyncByteStream)  # always true: we only use AsyncClient
    async for chunk in stream:
        yield chunk


async def _read_bounded(response: httpx.Response, limit: int, *, truncate: bool) -> bytes:
    encoding = response.headers.get("content-encoding", "identity").strip().lower()
    if encoding in ("", "identity"):
        decoder = None
    elif encoding in ("gzip", "x-gzip", "deflate"):
        decoder = zlib.decompressobj(zlib.MAX_WBITS | 32)
    else:
        raise FetchError(FetchFailure.NOT_EXTRACTABLE)

    body = bytearray()
    async for chunk in _iter_raw(response):
        if decoder is None:
            piece = chunk
        else:
            try:
                # max_length bounds memory: a bomb never inflates past the cap.
                piece = decoder.decompress(chunk, limit + 1 - len(body))
            except zlib.error:
                raise FetchError(FetchFailure.NOT_EXTRACTABLE) from None
        body += piece
        overflow = len(body) > limit or (decoder is not None and bool(decoder.unconsumed_tail))
        if overflow:
            if truncate:
                return bytes(body[:limit])
            raise FetchError(FetchFailure.TOO_LARGE)
    return bytes(body)


def _status_failure(response: httpx.Response, body: str) -> FetchFailure:
    status = response.status_code
    if status == 401:
        return FetchFailure.LOGIN_REQUIRED
    if status in (403, 429):
        return FetchFailure.BLOCKED_BY_SITE
    if status in (404, 410):
        return FetchFailure.EXPIRED
    if status == 503 and (
        response.headers.get("cf-mitigated") == "challenge" or looks_like_challenge(body)
    ):
        return FetchFailure.BLOCKED_BY_SITE
    if status >= 500:
        return FetchFailure.SITE_UNAVAILABLE
    return FetchFailure.NOT_EXTRACTABLE


async def _read_page(response: httpx.Response, url: PublicUrl) -> FetchResult:
    if not 200 <= response.status_code < 300:
        peek = await _read_bounded(response, MAX_PEEK_BYTES, truncate=True)
        raise FetchError(_status_failure(response, _decode(peek, response)))
    content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type not in TEXT_TYPES:
        raise FetchError(FetchFailure.NOT_EXTRACTABLE)
    declared = response.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > MAX_BODY_BYTES:
        raise FetchError(FetchFailure.TOO_LARGE)
    body = await _read_bounded(response, MAX_BODY_BYTES, truncate=False)
    return FetchResult(url=str(url), content_type=content_type, text=_decode(body, response))


class SafeFetcher:
    def __init__(
        self,
        *,
        resolver: Resolver = system_resolver,
        transport: httpx.AsyncBaseTransport | None = None,
        robots: RobotsCache | None = None,
        total_timeout: float = 15.0,
        robots_timeout: float = 5.0,
    ) -> None:
        self._resolver = resolver
        self._transport = transport
        self._robots = robots if robots is not None else _SHARED_ROBOTS
        self._total_timeout = total_timeout
        self._robots_timeout = robots_timeout

    def build_client(self) -> httpx.AsyncClient:
        # trust_env=False: an HTTP(S)_PROXY variable would connect for us, around the pinned IP.
        # cookies: a policy that allows no domain at all, so a Set-Cookie from robots.txt or a
        # redirect hop can never be stored or sent back on a later, possibly different-host,
        # request pinned to the same IP.
        no_cookies = http.cookiejar.CookieJar(
            policy=http.cookiejar.DefaultCookiePolicy(allowed_domains=[])
        )
        return httpx.AsyncClient(
            transport=self._transport,
            trust_env=False,
            follow_redirects=False,
            timeout=_TIMEOUT,
            cookies=no_cookies,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,text/plain;q=0.9",
                "Accept-Encoding": "gzip, deflate",
            },
        )

    async def fetch(self, raw_url: str) -> FetchResult:
        url = parse_public_url(raw_url)
        async with self.build_client() as client:
            try:
                async with asyncio.timeout(self._total_timeout):
                    response, final = await self._open(client, url, check_robots=True)
                    try:
                        return await _read_page(response, final)
                    finally:
                        await response.aclose()
            except TimeoutError, httpx.TimeoutException:
                raise FetchError(FetchFailure.FETCH_TIMEOUT) from None
            except httpx.HTTPError:
                raise FetchError(FetchFailure.SITE_UNAVAILABLE) from None

    async def _open(
        self, client: httpx.AsyncClient, url: PublicUrl, *, check_robots: bool
    ) -> tuple[httpx.Response, PublicUrl]:
        for _ in range(MAX_REDIRECTS + 1):
            if check_robots and not await self._robots_allow(client, url):
                raise FetchError(FetchFailure.BLOCKED_BY_ROBOTS)
            response = await self._send_pinned(client, url)
            if not response.is_redirect:
                return response, url
            location = response.headers.get("location", "")
            await response.aclose()
            if not location:
                raise FetchError(FetchFailure.NOT_EXTRACTABLE)
            url = parse_public_url(urljoin(str(url), location))
        raise FetchError(FetchFailure.NOT_EXTRACTABLE)

    async def _send_pinned(self, client: httpx.AsyncClient, url: PublicUrl) -> httpx.Response:
        try:
            addresses = await self._resolver(url.host, _PORTS[url.scheme])
        except socket.gaierror, UnicodeError:
            raise FetchError(FetchFailure.INVALID_URL) from None
        if not addresses or not all(is_public_address(address) for address in addresses):
            raise FetchError(FetchFailure.BLOCKED_ADDRESS)
        # Connect to the address that was checked; the hostname travels only as Host and SNI,
        # so a second DNS answer (rebinding) can never be used for the connection.
        request = client.build_request(
            "GET",
            f"{url.scheme}://{_netloc(addresses[0])}{url.target}",
            headers={"Host": url.netloc},
            extensions={"sni_hostname": url.host} if url.scheme == "https" else {},
        )
        try:
            # httpx pre-parses a redirect's Location into a next request to populate
            # response.next_request, even though follow_redirects=False means it never
            # sends it — so a malformed Location can raise here, before we ever read it.
            return await client.send(request, stream=True)
        except httpx.InvalidURL:
            raise FetchError(FetchFailure.INVALID_URL) from None
        except httpx.RemoteProtocolError as exc:
            if str(exc).startswith(_INVALID_LOCATION_PREFIX):
                raise FetchError(FetchFailure.INVALID_URL) from None
            raise

    async def _robots_allow(self, client: httpx.AsyncClient, url: PublicUrl) -> bool:
        now = time.monotonic()
        parser = self._robots.get(url.origin, now)
        if parser is None:
            parser, cacheable = await self._load_robots(client, url)
            if cacheable:
                self._robots.put(url.origin, parser, now)
        return parser.can_fetch(USER_AGENT_TOKEN, str(url))

    async def _load_robots(
        self, client: httpx.AsyncClient, url: PublicUrl
    ) -> tuple[RobotFileParser, bool]:
        robots_url = PublicUrl(url.scheme, url.host, "/robots.txt")
        try:
            async with asyncio.timeout(self._robots_timeout):
                response, _ = await self._open(client, robots_url, check_robots=False)
                try:
                    if 400 <= response.status_code < 500:
                        return _rules(_ALLOW_ALL), True
                    if 200 <= response.status_code < 300:
                        body = await _read_bounded(response, MAX_ROBOTS_BYTES, truncate=True)
                        return _rules(_decode(body, response).splitlines()), True
                finally:
                    await response.aclose()
        except FetchError as exc:
            if exc.failure in (FetchFailure.BLOCKED_ADDRESS, FetchFailure.INVALID_URL):
                raise
        except TimeoutError, httpx.TimeoutException:
            # A transport failure is a real, reportable reason, not a robots verdict — the
            # page is still never fetched, but the caller learns why, not a made-up "disallow".
            raise FetchError(FetchFailure.FETCH_TIMEOUT) from None
        except httpx.HTTPError:
            raise FetchError(FetchFailure.SITE_UNAVAILABLE) from None
        # RFC 9309: a server error or an unreachable robots.txt means disallow everything.
        # Not cached, so the next attempt asks again.
        return _rules(_DISALLOW_ALL), False
