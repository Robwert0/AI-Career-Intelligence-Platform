import pytest

from app.ai.grounding import invents_facts, ungrounded_terms

CV = (
    "Robert Mirea\n"
    "Junior Software Engineer — Tyrell Corporation | Nov 2025 – Present\n"
    "Software Developer (Internship) — BearingPoint | Jul 2024 – Sep 2024\n"
    "Skills: Python, FastAPI, PostgreSQL, Redis, RabbitMQ"
)


@pytest.mark.parametrize(
    ("answer", "terms"),
    [
        ("Robert worked at NASA. He worked at Tyrell Corporation.", ["NASA"]),
        ("Robert led a team of 40 engineers at Google.", ["40", "Google"]),
        ("He has twelve years of experience with Python.", ["twelve"]),
        ("He has worked at Tyrell Corporation since 2019.", ["2019"]),
        ("He holds a PhD from MIT.", ["PhD", "MIT"]),
        ("He started in March 2025.", ["March"]),
    ],
)
def test_names_and_figures_the_cv_never_mentions_are_ungrounded(
    answer: str, terms: list[str]
) -> None:
    assert ungrounded_terms(CV, answer) == terms


@pytest.mark.parametrize(
    "answer",
    [
        "His current role is Junior Software Engineer at Tyrell Corporation.",
        "He has been at Tyrell Corporation since November 2025.",
        "He was a Software Developer Intern at BearingPoint.",
        "He has completed two internships: one at BearingPoint.",
        "According to the CV, Robert Mirea uses Python and FastAPI.",
        "Yes. He has used PostgreSQL and Redis in production.",
        "The candidate has worked with RabbitMQ as a message broker.",
    ],
)
def test_ordinary_answers_from_the_cv_are_grounded(answer: str) -> None:
    assert ungrounded_terms(CV, answer) == []


def test_each_term_is_reported_once_in_order() -> None:
    assert ungrounded_terms(CV, "NASA, then Google, then NASA again.") == ["NASA", "Google"]


def test_the_rewrite_guard_keeps_its_strict_rules() -> None:
    assert invents_facts("Joined in Nov 2025.", "Joined in November 2025.")
    assert invents_facts("Built two services.", "Built three services.")
    assert not invents_facts("Built services on PostgreSQL.", "Built PostgreSQL services.")
