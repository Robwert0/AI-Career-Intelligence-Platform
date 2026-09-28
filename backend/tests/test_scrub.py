import pytest

from app.ai.match.scrub import EMAIL_PLACEHOLDER, mentions_sensitive, scrub_evidence_text
from app.ai.redaction import PHONE_PLACEHOLDER


@pytest.mark.parametrize(
    "sentence",
    [
        "Date of birth: 12.03.1990.",
        "DOB 1990-03-12.",
        "Born in Bucharest in 1990.",
        "34 years old.",
        "Age: 34.",
        "Marital status: married, two children.",
        "Nationality: Romanian.",
        "EU citizenship.",
        "Religion: Orthodox.",
        "Gender: male.",
        "Passport number: X1234567.",
        "CNP 1900312123456.",
        "Photo attached.",
    ],
)
def test_a_sentence_naming_a_sensitive_characteristic_is_dropped(sentence: str) -> None:
    scrubbed = scrub_evidence_text(f"Built Go payment services. {sentence} Led a team of 4.")

    assert scrubbed == "Built Go payment services. Led a team of 4."


def test_contact_details_are_masked() -> None:
    scrubbed = scrub_evidence_text("Reach me at jane.doe+cv@mail.example.com or +40 721 234 567.")

    assert EMAIL_PLACEHOLDER in scrubbed
    assert PHONE_PLACEHOLDER in scrubbed
    assert "jane.doe" not in scrubbed
    assert "721" not in scrubbed


@pytest.mark.parametrize(
    "text",
    [
        "Built a single-page app for healthcare scheduling, 2019-2023.",
        "Designed the age-verification API used by 3 million users.",
        "Migrated 40,000,000 rows to PostgreSQL 16.",
    ],
)
def test_ordinary_work_text_is_kept(text: str) -> None:
    assert scrub_evidence_text(text) == text


def test_bullet_separated_details_are_scrubbed_piece_by_piece() -> None:
    scrubbed = scrub_evidence_text("Go · Nationality: Romanian · PostgreSQL")

    assert scrubbed == "Go PostgreSQL"


def test_text_that_is_only_sensitive_becomes_empty() -> None:
    assert scrub_evidence_text("Nationality: Romanian. Marital status: single.") == ""


def test_a_label_is_checked_whole() -> None:
    assert mentions_sensitive("Personal details · Nationality")
    assert not mentions_sensitive("Experience · Acme")


# --- H1: every §5.4 category, from the audit's own probe list ----------------------------


@pytest.mark.parametrize(
    "sentence",
    [
        "Age 34, based in Oslo",
        "Born 1990",
        "34 y/o engineer",
        "Place of birth: Cluj",
        "Ethnicity: Roma",
        "Race: Black",
        "Visa status: H-1B",
        "Work permit required",
        "Health: diabetic",
        "Two children",
        "Father of two",
        "Wife and kids",
        "Sexual orientation: gay",
        "Transgender advocate",
        "Muslim, practising",
        "Mother tongue: Hungarian",
        "Nationalitate: română",
    ],
)
def test_every_5_4_category_from_the_audit_probe_is_dropped(sentence: str) -> None:
    scrubbed = scrub_evidence_text(f"Built Go payment services. {sentence}. Led a team of 4.")

    assert scrubbed == "Built Go payment services. Led a team of 4."


# --- M3: the same regex must not delete legitimate skills evidence -----------------------


@pytest.mark.parametrize(
    "text",
    [
        "Photoshop and Illustrator expert",
        "Disabled legacy endpoints to cut cost",
        "Built a healthcare API used by 3 million patients",
        "Race condition in the scheduler was diagnosed and fixed",
        "Integrated Visa and Mastercard payment APIs",
        "Embraced test-driven development for the whole team",
    ],
)
def test_the_wider_5_4_coverage_still_keeps_ordinary_text(text: str) -> None:
    assert scrub_evidence_text(text) == text
