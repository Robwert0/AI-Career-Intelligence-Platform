import pytest

from app.integrations.errors import FetchFailure
from app.services.match_failures import _FAILURES, describe_failure


def test_an_overlong_posting_asks_for_a_shorter_paste() -> None:
    failure = describe_failure("input_too_long")

    assert (failure.code, failure.recovery) == ("input_too_long", "paste")
    assert "too long" in failure.message


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


@pytest.mark.parametrize(
    "code", [*(failure.value for failure in FetchFailure), *_INTAKE_WORKER_CODES]
)
def test_every_intake_code_has_its_own_catalogue_entry(code: str) -> None:
    assert code in _FAILURES


def test_an_unknown_code_falls_back_to_the_internal_error_wording() -> None:
    failure = describe_failure("never_heard_of_it")

    assert (failure.code, failure.recovery) == ("never_heard_of_it", "retry")
    assert failure.message == "Something went wrong on our side. Try again."
