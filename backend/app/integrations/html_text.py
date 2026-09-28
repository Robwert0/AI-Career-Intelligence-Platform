import json
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any

from app.integrations.errors import FetchFailure

MIN_READABLE_CHARS = 500
_CHALLENGE_MAX_CHARS = 2000
_LOGIN_WALL_MAX_CHARS = 1500
_SKIP = frozenset({"script", "style", "noscript", "svg", "template", "head", "iframe", "object"})
_BLOCK = frozenset(
    {
        "address",
        "article",
        "aside",
        "blockquote",
        "br",
        "dd",
        "div",
        "dl",
        "dt",
        "footer",
        "form",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "hr",
        "li",
        "main",
        "nav",
        "ol",
        "p",
        "pre",
        "section",
        "table",
        "td",
        "th",
        "tr",
        "ul",
    }
)
_CHALLENGE_MARKERS = (
    "cf-chl",
    "/cdn-cgi/challenge-platform/",
    "_incapsula_resource",
    "px-captcha",
    "captcha-delivery.com",
    "just a moment...",
)
_SPACES = re.compile(r"[ \t\f\v\r ]+")


@dataclass(frozen=True, slots=True)
class LinkedPosting:
    title: str | None
    company: str | None
    description: str


@dataclass(frozen=True, slots=True)
class Page:
    title: str | None
    text: str
    posting: LinkedPosting | None
    has_password_input: bool
    challenge_marked: bool


class _Extractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.title_parts: list[str] = []
        self.ld_blocks: list[list[str]] = []
        self.has_password_input = False
        self._skip_depth = 0
        self._in_title = False
        self._in_ld = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {name: (value or "") for name, value in attrs}
        if tag == "input" and attributes.get("type", "").lower() == "password":
            self.has_password_input = True
        if tag == "script" and attributes.get("type", "").lower() == "application/ld+json":
            self._in_ld = True
            self.ld_blocks.append([])
            return
        if tag == "title":
            self._in_title = True
        if tag in _SKIP:
            self._skip_depth += 1
        elif tag in _BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._in_ld:
            self._in_ld = False
            return
        if tag == "title":
            self._in_title = False
        if tag in _SKIP:
            self._skip_depth = max(0, self._skip_depth - 1)
        elif tag in _BLOCK:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._in_ld:
            self.ld_blocks[-1].append(data)
        elif self._in_title:
            self.title_parts.append(data)
        elif not self._skip_depth:
            self.parts.append(data)


def _normalise(text: str) -> str:
    lines = (_SPACES.sub(" ", line).strip() for line in text.split("\n"))
    return "\n".join(line for line in lines if line)


def _html_to_text(html: str) -> str:
    extractor = _Extractor()
    extractor.feed(html)
    extractor.close()
    return _normalise("".join(extractor.parts))


def _job_postings(node: Any) -> list[dict[str, Any]]:
    if isinstance(node, list):
        return [found for item in node for found in _job_postings(item)]
    if not isinstance(node, dict):
        return []
    if "@graph" in node:
        return _job_postings(node["@graph"])
    kind = node.get("@type")
    kinds = kind if isinstance(kind, list) else [kind]
    return [node] if "JobPosting" in kinds else []


def _linked_posting(blocks: list[list[str]]) -> LinkedPosting | None:
    for block in blocks:
        try:
            data = json.loads("".join(block))
        except ValueError:
            continue
        for posting in _job_postings(data):
            organisation = posting.get("hiringOrganization")
            company = organisation.get("name") if isinstance(organisation, dict) else organisation
            description = posting.get("description")
            title = posting.get("title")
            return LinkedPosting(
                title=title.strip() if isinstance(title, str) else None,
                company=company.strip() if isinstance(company, str) else None,
                description=_html_to_text(description) if isinstance(description, str) else "",
            )
    return None


def extract_page(html: str) -> Page:
    extractor = _Extractor()
    extractor.feed(html)
    extractor.close()
    title = _normalise("".join(extractor.title_parts)) or None
    return Page(
        title=title,
        text=_normalise("".join(extractor.parts)),
        posting=_linked_posting(extractor.ld_blocks),
        has_password_input=extractor.has_password_input,
        challenge_marked=looks_like_challenge(html),
    )


def plain_page(text: str) -> Page:
    return Page(
        title=None,
        text=_normalise(text),
        posting=None,
        has_password_input=False,
        challenge_marked=False,
    )


def looks_like_challenge(html: str) -> bool:
    lowered = html.lower()
    return any(marker in lowered for marker in _CHALLENGE_MARKERS)


def job_text(page: Page) -> str:
    posting = page.posting
    if posting is not None and len(posting.description) >= MIN_READABLE_CHARS:
        header = [f"Title: {posting.title}"] if posting.title else []
        if posting.company:
            header.append(f"Company: {posting.company}")
        return "\n".join([*header, posting.description])
    return "\n".join(part for part in (page.title, page.text) if part)


def page_failure(page: Page) -> FetchFailure | None:
    # Markers alone are not enough: Cloudflare injects its challenge script into normal pages.
    if page.challenge_marked and len(page.text) < _CHALLENGE_MAX_CHARS:
        return FetchFailure.BLOCKED_BY_SITE
    if page.has_password_input and len(page.text) < _LOGIN_WALL_MAX_CHARS:
        return FetchFailure.LOGIN_REQUIRED
    if len(job_text(page)) < MIN_READABLE_CHARS:
        return FetchFailure.NOT_EXTRACTABLE
    return None
