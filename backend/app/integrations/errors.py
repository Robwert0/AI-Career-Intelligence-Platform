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
