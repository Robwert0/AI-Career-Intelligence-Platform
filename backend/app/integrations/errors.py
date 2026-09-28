from enum import StrEnum

FetchFailure = StrEnum(
    "FetchFailure",
    (
        "INVALID_URL",
        "BLOCKED_ADDRESS",
        "BLOCKED_BY_ROBOTS",
        "BLOCKED_BY_SITE",
        "LOGIN_REQUIRED",
        "EXPIRED",
        "NOT_EXTRACTABLE",
        "FETCH_TIMEOUT",
        "TOO_LARGE",
        "SITE_UNAVAILABLE",
    ),
)


class FetchError(Exception):
    def __init__(self, failure: FetchFailure) -> None:
        super().__init__(failure.value)
        self.failure = failure


DocumentFailure = StrEnum(
    "DocumentFailure",
    (
        "FILE_TOO_LARGE",
        "UNSUPPORTED_TYPE",
        "ENCRYPTED_PDF",
        "TOO_MANY_PAGES",
        "UNSAFE_DOCX",
        "SCANNED_PDF_SUSPECTED",
        "UNREADABLE_DOCUMENT",
    ),
)


class DocumentError(Exception):
    def __init__(self, failure: DocumentFailure) -> None:
        super().__init__(failure.value)
        self.failure = failure


GitHubFailure = StrEnum(
    "GitHubFailure",
    (
        "INVALID_GITHUB_URL",
        "GITHUB_USER_NOT_FOUND",
        "GITHUB_RATE_LIMITED",
        "GITHUB_UNAVAILABLE",
    ),
)


class GitHubError(Exception):
    def __init__(self, failure: GitHubFailure, *, reset_at: int | None = None) -> None:
        super().__init__(failure.value)
        self.failure = failure
        self.reset_at = reset_at
