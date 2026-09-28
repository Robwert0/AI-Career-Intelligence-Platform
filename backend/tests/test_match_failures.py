import pytest

from app.integrations.errors import DocumentFailure, FetchFailure, GitHubFailure
from app.services.match_failures import _FAILURES, describe_failure


def test_an_overlong_posting_asks_for_a_shorter_paste() -> None:
    failure = describe_failure("input_too_long")

    assert (failure.code, failure.recovery) == ("input_too_long", "paste")
    assert "too long" in failure.message


def test_not_a_cv_recovers_by_pasting_the_cv_text() -> None:
    # The backend previously offered choose_file, but pasting is the only recovery that never
    # asks the user to re-upload the same rejected file.
    failure = describe_failure("not_a_cv")

    assert failure.recovery == "paste_cv"


_INTAKE_WORKER_CODES = [
    "input_expired",
    "worker_lost",
    "timeout",
    "ai_unavailable",
    "ai_invalid_output",
    "input_too_long",
    "not_a_job_posting",
    "queue_unavailable",
    "internal_error",
    "not_found",
    "unavailable",
    "job_in_progress",
]
# The candidate-evidence side of the catalogue (slice 3): every failure code read_cv/read_github
# can raise, plus the cv-specific extraction codes not shared with job intake.
_CANDIDATE_CODES = [
    *(failure.value for failure in DocumentFailure),
    *(failure.value for failure in GitHubFailure),
    "not_a_cv",
    "cv_ai_invalid_output",
    "cv_input_too_long",
    "cv_no_evidence",
]


@pytest.mark.parametrize(
    "code",
    [*(failure.value for failure in FetchFailure), *_INTAKE_WORKER_CODES, *_CANDIDATE_CODES],
)
def test_every_intake_code_has_its_own_catalogue_entry(code: str) -> None:
    assert code in _FAILURES


def test_an_unknown_code_falls_back_to_the_internal_error_wording() -> None:
    failure = describe_failure("never_heard_of_it")

    assert (failure.code, failure.recovery) == ("never_heard_of_it", "retry")
    assert failure.message == "Something went wrong on our side. Try again."


def test_a_reset_time_is_added_to_the_message_in_utc() -> None:
    described = describe_failure("github_rate_limited", retry_at=1790000000)

    assert described.message.endswith("You can retry after 14:13 UTC.")
    assert described.recovery == describe_failure("github_rate_limited").recovery


_ANALYSIS_CODES = [
    "no_candidate_source",
    "cv_and_cv_text",
    "consent_required",
    "invalid_job",
    "analysis_in_progress",
    "not_awaiting_decision",
    "analysis_not_found",
    "queue_full",
    "analysis_discarded",
    "analysis_running",
]


@pytest.mark.parametrize("code", _ANALYSIS_CODES)
def test_every_analysis_code_has_its_own_catalogue_entry(code: str) -> None:
    assert code in _FAILURES
