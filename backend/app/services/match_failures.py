from app.schemas.match import FailureOut, Recovery

_PASTE: Recovery = "paste"
_FAILURES: dict[str, tuple[str, Recovery]] = {
    "invalid_url": (
        "That doesn't look like a public job posting link. Check the URL, or paste "
        "the job description instead.",
        "fix_url",
    ),
    "blocked_address": (
        "That link points to a private or internal address, so it can't be "
        "fetched. Paste the job description instead.",
        _PASTE,
    ),
    "blocked_by_robots": (
        "This site doesn't allow automated access to its job pages. Paste the "
        "job description instead.",
        _PASTE,
    ),
    "blocked_by_site": (
        "This site blocks automated access. Paste the job description instead.",
        _PASTE,
    ),
    "login_required": (
        "This posting is behind a login. Paste the job description instead.",
        _PASTE,
    ),
    "expired": (
        "This posting seems to have been removed or has expired. If you still have the "
        "text, paste it instead.",
        _PASTE,
    ),
    "not_extractable": (
        "We couldn't read a job description from that page. Paste the job description instead.",
        _PASTE,
    ),
    "fetch_timeout": (
        "The site took too long to respond. Try again, or paste the job description instead.",
        _PASTE,
    ),
    "input_too_long": (
        "This posting is too long to analyse. Paste just the role description and requirements.",
        _PASTE,
    ),
    "too_large": ("That page is too large to read. Paste the job description instead.", _PASTE),
    "site_unavailable": (
        "We couldn't reach that site. Try again later, or paste the job description instead.",
        _PASTE,
    ),
    "not_a_job_posting": (
        "That doesn't look like a job posting. Check the link or the text you pasted.",
        "fix_url",
    ),
    "ai_unavailable": (
        "The analysis model is unavailable right now. Try again in a few minutes.",
        "retry",
    ),
    "ai_invalid_output": (
        "We couldn't extract this posting reliably. Try again, or paste a "
        "cleaner copy of the description.",
        "retry",
    ),
    "timeout": ("This took too long and was stopped. Try again.", "retry"),
    "queue_unavailable": (
        "Background processing is unavailable right now. Try again in a few minutes.",
        "wait",
    ),
    "worker_lost": ("Processing was interrupted. Try again.", "retry"),
    "input_expired": ("This request expired before it was processed. Submit it again.", "retry"),
    "not_found": ("We couldn't find that job. It may have expired or already finished.", "retry"),
    "unavailable": ("This service is temporarily unavailable. Try again in a few minutes.", "wait"),
}
_FALLBACK: tuple[str, Recovery] = ("Something went wrong on our side. Try again.", "retry")


def describe_failure(code: str) -> FailureOut:
    message, recovery = _FAILURES.get(code, _FALLBACK)
    return FailureOut(code=code, message=message, recovery=recovery)
