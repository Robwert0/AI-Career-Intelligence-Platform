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
