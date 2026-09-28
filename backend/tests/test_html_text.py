import json

import pytest

from app.integrations.errors import FetchFailure
from app.integrations.html_text import (
    MIN_READABLE_CHARS,
    extract_page,
    job_text,
    looks_like_challenge,
    page_failure,
    plain_page,
)

BODY = "We build payment systems in Go and PostgreSQL. " * 20


def html(body: str, head: str = "") -> str:
    return f"<html><head><title>Backend Engineer</title>{head}</head><body>{body}</body></html>"


def ld(payload: object) -> str:
    return f'<script type="application/ld+json">{json.dumps(payload)}</script>'


def test_scripts_styles_and_head_never_reach_the_text() -> None:
    page = extract_page(
        html(
            "<style>.x{color:red}</style><p>Visible</p><script>var secret = 1;</script>",
            head="<meta name='x' content='y'><script>track()</script>",
        )
    )

    assert page.text == "Visible"
    assert page.title == "Backend Engineer"


def test_block_elements_become_lines_and_whitespace_collapses() -> None:
    page = extract_page(html("<h1>Role</h1><ul><li>Go</li><li>SQL   and\tRedis</li></ul>"))

    assert page.text.splitlines() == ["Role", "Go", "SQL and Redis"]


def test_entities_are_decoded() -> None:
    assert extract_page(html("<p>R&amp;D &lt;team&gt;</p>")).text == "R&D <team>"


def test_non_breaking_spaces_collapse_like_other_whitespace() -> None:
    page = extract_page(html("<p>Salary:&nbsp;&nbsp;$100k</p>"))

    assert page.text == "Salary: $100k"


def test_a_json_ld_job_posting_is_extracted() -> None:
    posting = {
        "@context": "https://schema.org",
        "@type": "JobPosting",
        "title": "Senior Backend Engineer",
        "hiringOrganization": {"@type": "Organization", "name": "Acme"},
        "description": f"<p>{BODY}</p><ul><li>5 years of Go</li></ul>",
    }

    page = extract_page(html("<p>short</p>", head=ld(posting)))

    assert page.posting is not None
    assert (page.posting.title, page.posting.company) == ("Senior Backend Engineer", "Acme")
    assert "5 years of Go" in page.posting.description
    assert "<li>" not in page.posting.description


@pytest.mark.parametrize("shape", ["graph", "list"])
def test_a_job_posting_inside_a_graph_or_list_is_found(shape: str) -> None:
    posting = {"@type": "JobPosting", "title": "SRE", "description": BODY}
    payload: object = (
        {"@graph": [{"@type": "WebPage"}, posting]}
        if shape == "graph"
        else [{"@type": "BreadcrumbList"}, posting]
    )

    page = extract_page(html("", head=ld(payload)))

    assert page.posting is not None
    assert page.posting.title == "SRE"


def test_broken_json_ld_is_ignored() -> None:
    page = extract_page(
        html(f"<p>{BODY}</p>", head='<script type="application/ld+json">{not json</script>')
    )

    assert page.posting is None
    assert BODY.strip() in page.text


def test_a_deeply_nested_json_ld_does_not_crash_extraction() -> None:
    deeply_nested = "[" * 999 + "]" * 999
    head = f'<script type="application/ld+json">{deeply_nested}</script>'
    page = extract_page(html(f"<p>{BODY}</p>", head=head))

    assert page.posting is None
    assert BODY.strip() in page.text


def test_a_job_posting_nested_inside_a_graph_and_a_list_is_still_found() -> None:
    posting = {"@type": "JobPosting", "title": "SRE", "description": BODY}
    payload = {"@graph": [[posting]]}

    page = extract_page(html("", head=ld(payload)))

    assert page.posting is not None
    assert page.posting.title == "SRE"


def test_job_text_prefers_a_substantial_json_ld_description() -> None:
    posting = {
        "@type": "JobPosting",
        "title": "SRE",
        "hiringOrganization": "Acme",
        "description": BODY,
    }

    text = job_text(extract_page(html("<nav>Home Jobs Login</nav>", head=ld(posting))))

    assert text.startswith("Title: SRE\nCompany: Acme\n")
    assert "Home Jobs Login" not in text


def test_job_text_falls_back_to_the_page_when_json_ld_is_thin() -> None:
    posting = {"@type": "JobPosting", "title": "SRE", "description": "See below."}

    text = job_text(extract_page(html(f"<p>{BODY}</p>", head=ld(posting))))

    assert BODY.strip() in text


def test_a_short_challenge_page_is_blocked_by_site() -> None:
    page = extract_page(
        html("<p>Just a moment...</p><script src='/cdn-cgi/challenge-platform/h/b'></script>")
    )

    assert page_failure(page) is FetchFailure.BLOCKED_BY_SITE


def test_a_real_posting_served_through_cloudflare_is_not_a_challenge() -> None:
    # Cloudflare injects its challenge-platform script into ordinary pages too.
    page = extract_page(
        html(
            f"<p>{BODY * 3}</p><script src='/cdn-cgi/challenge-platform/scripts/jsd/main.js'>"
            "</script>"
        )
    )

    assert page_failure(page) is None


def test_a_short_page_with_a_password_field_is_a_login_wall() -> None:
    page = extract_page(
        html("<form><input name='u'><input type='PASSWORD' name='p'></form><p>Sign in</p>")
    )

    assert page_failure(page) is FetchFailure.LOGIN_REQUIRED


def test_a_page_with_too_little_text_is_not_extractable() -> None:
    assert page_failure(extract_page(html("<div id='app'></div>"))) is (
        FetchFailure.NOT_EXTRACTABLE
    )


def test_a_readable_posting_has_no_failure() -> None:
    assert page_failure(extract_page(html(f"<p>{BODY}</p>"))) is None


def test_plain_text_is_normalised_and_classified_the_same_way() -> None:
    page = plain_page("  Role:\tBackend\r\n\r\n" + BODY)

    assert page.text.startswith("Role: Backend\n")
    assert page_failure(page) is None
    assert page_failure(plain_page("too short")) is FetchFailure.NOT_EXTRACTABLE


@pytest.mark.parametrize(
    "marker",
    [
        "cf-chl-opt",
        "/cdn-cgi/challenge-platform/",
        "_Incapsula_Resource",
        "px-captcha",
        "captcha-delivery.com",
    ],
)
def test_challenge_markers_are_recognised(marker: str) -> None:
    assert looks_like_challenge(f"<html>{marker}</html>")


def test_min_readable_chars_is_the_documented_floor() -> None:
    assert MIN_READABLE_CHARS == 500
