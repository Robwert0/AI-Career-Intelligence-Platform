import pytest

from app.ai.match.requirements import requirement_is_sensitive, requirement_refs
from app.ai.match.schemas import JobPosting, Requirement


def posting(*texts: str) -> JobPosting:
    return JobPosting(
        title="Backend Engineer",
        required=[Requirement(text=text, sensitive=False) for text in texts],
    )


def test_the_server_rechecks_a_requirement_the_client_marked_not_sensitive() -> None:
    [age, skill] = requirement_refs(posting("Must be under 35", "5 years of Go"))

    assert (age.sensitive, skill.sensitive) == (True, False)


@pytest.mark.parametrize(
    "text",
    [
        "Must be under 35",
        "Candidates aged 25-35",
        "Younger than 40",
        "Between 25 and 35 years old",
        "EU work permit",
        "Male candidates only",
    ],
)
def test_personal_characteristics_are_sensitive(text: str) -> None:
    assert requirement_is_sensitive(text)


@pytest.mark.parametrize(
    "text",
    [
        "Keep p99 latency under 50 ms",
        "Over 10 years of Python experience",
        "Lead teams of under 10 people",
        "5+ years of Go",
        "Experience with Kubernetes",
    ],
)
def test_ordinary_requirements_stay_assessable(text: str) -> None:
    assert not requirement_is_sensitive(text)


def test_a_client_flag_is_never_lowered() -> None:
    flagged = JobPosting(
        title="Backend Engineer", required=[Requirement(text="Go", sensitive=True)]
    )

    assert requirement_refs(flagged)[0].sensitive is True
