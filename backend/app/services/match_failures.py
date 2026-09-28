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
    "job_in_progress": (
        "You already have a job posting being read. Wait for it to finish, then try again.",
        "wait",
    ),
    "queue_unavailable": (
        "Background processing is unavailable right now. Try again in a few minutes.",
        "wait",
    ),
    "worker_lost": ("Processing was interrupted. Try again.", "retry"),
    "input_expired": ("This request expired before it was processed. Submit it again.", "retry"),
    "not_found": ("We couldn't find that job. It may have expired or already finished.", "retry"),
    "unavailable": ("This service is temporarily unavailable. Try again in a few minutes.", "wait"),
    "internal_error": ("Something went wrong on our side. Try again.", "retry"),
    "file_too_large": (
        "That file is larger than the upload limit. Choose a smaller file, or "
        "paste your CV text instead.",
        "choose_file",
    ),
    "unsupported_type": (
        "Only PDF and Word (.docx) files can be read. Choose another file, or "
        "paste your CV text instead.",
        "choose_file",
    ),
    "encrypted_pdf": (
        "That PDF is password-protected. Save an unprotected copy and upload that, "
        "or paste your CV text instead.",
        "choose_file",
    ),
    "too_many_pages": (
        "That PDF has more than 10 pages. Upload a shorter CV, or paste the relevant part instead.",
        "choose_file",
    ),
    "unsafe_docx": (
        "That Word file contains macros or an unusual structure we don't open. Save "
        "it as a plain .docx or PDF and upload that instead.",
        "choose_file",
    ),
    "scanned_pdf_suspected": (
        "That PDF looks like a scanned image with no readable text. Upload "
        "a text-based PDF, or paste your CV text instead.",
        "paste_cv",
    ),
    "unreadable_document": (
        "We couldn't read text from that file. Upload a text-based PDF or "
        ".docx, or paste your CV text instead.",
        "paste_cv",
    ),
    "not_a_cv": (
        "That document doesn't look like a CV. Check the file, or paste your CV text instead.",
        "choose_file",
    ),
    "invalid_github_url": (
        "Enter a GitHub profile link like https://github.com/your-name.",
        "fix_github_url",
    ),
    "github_user_not_found": (
        "There's no GitHub user with that name. Check the link, or continue without GitHub.",
        "fix_github_url",
    ),
    "github_rate_limited": (
        "GitHub is limiting how often we can read profiles right now. Try "
        "again later, or continue without GitHub.",
        "retry_or_continue",
    ),
    "github_unavailable": (
        "We couldn't reach GitHub. Try again, or continue without GitHub.",
        "retry_or_continue",
    ),
}
_FALLBACK: tuple[str, Recovery] = _FAILURES["internal_error"]


def describe_failure(code: str) -> FailureOut:
    message, recovery = _FAILURES.get(code, _FALLBACK)
    return FailureOut(code=code, message=message, recovery=recovery)
