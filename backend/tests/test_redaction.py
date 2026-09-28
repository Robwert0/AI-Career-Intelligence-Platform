import pytest

from app.ai.redaction import PHONE_PLACEHOLDER, redact_phone_numbers


@pytest.mark.parametrize(
    "phone",
    [
        "(+40) 700 000 000",
        "+40 700 000 000",
        "+40700000000",
        "0700 000 000",
        "0700-000-000",
        "0700.000.000",
        "(0700) 000 000",
        "+1 (555) 010-0000",
    ],
)
def test_a_phone_number_is_replaced_in_any_common_format(phone: str) -> None:
    text = f"Jane Doe | {phone} | jane@example.com"

    assert redact_phone_numbers(text) == f"Jane Doe | {PHONE_PLACEHOLDER} | jane@example.com"


@pytest.mark.parametrize(
    "text",
    [
        "Jun 2024 – Aug 2024",
        "2021 - 2025",
        "2021-2025",
        "Python 3.12",
        "6-DOF robotic arm",
        "linkedin.com/in/jane-doe-413a91222",
        "github.com/Robwert0",
        "Built 12 services, 3 queues",
    ],
)
def test_dates_versions_and_urls_survive(text: str) -> None:
    assert redact_phone_numbers(text) == text


def test_numbers_on_separate_lines_are_not_joined_into_one() -> None:
    text = "Oct 2025 – Present\n2021 – 2025\n1 2 3"

    assert redact_phone_numbers(text) == text


def test_every_number_in_the_text_is_redacted() -> None:
    text = "mobile 0700 000 000, office +40 21 000 0000"

    assert redact_phone_numbers(text).count(PHONE_PLACEHOLDER) == 2


@pytest.mark.parametrize("phone", ["12 34 56 78", "2345 6789"])
def test_an_eight_digit_spaced_number_is_redacted(phone: str) -> None:
    text = f"Call {phone} for support"

    redacted = redact_phone_numbers(text)

    assert PHONE_PLACEHOLDER in redacted
    assert phone not in redacted


@pytest.mark.parametrize(
    "text",
    ["2021 - 2025", "2021-2025", "Oct 2025 – Present\n2021 – 2025\n1 2 3"],
)
def test_a_hyphenated_eight_digit_run_still_survives_as_a_date_range(text: str) -> None:
    # An 8-digit run split by a hyphen ("2021 - 2025") is a date range, never how a phone
    # number is grouped ("12 34 56 78"), so it must not be swept up by the new 8-digit rule.
    assert redact_phone_numbers(text) == text


def test_a_date_followed_by_an_unrelated_number_is_not_swept_into_one_run() -> None:
    # "Last pushed 2026-08. 12 stars": the period-space bridge that lets dot-separated phone
    # groups match ("0700.000.000") must not pull an unrelated later number into the same run.
    text = "Last pushed 2026-08. 12 stars"

    assert redact_phone_numbers(text) == text


def test_a_hyphenated_hong_kong_phone_number_is_redacted() -> None:
    # "2345-6789" is structurally identical to "2021-2025" (two hyphenated 4-digit groups);
    # what tells them apart is that neither half of a real phone number is a plausible year.
    text = "Call 2345-6789 for support"

    redacted = redact_phone_numbers(text)

    assert PHONE_PLACEHOLDER in redacted
    assert "2345-6789" not in redacted
