import random
import re
import time
from pathlib import Path

import pytest

from app.ai.grounding import _WORD, _names, invents_facts, ungrounded_terms

FIXTURES = Path(__file__).parent / "fixtures"

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


SENTENCE_START = re.compile(r"(?:^|[.!?;:]\s+)$")


def _regex_names(text: str) -> list[tuple[str, bool]]:
    return [
        (m.group(), bool(SENTENCE_START.search(text[: m.start()]))) for m in _WORD.finditer(text)
    ]


def test_sentence_starts_match_the_original_regex_rule() -> None:
    samples = [
        CV,
        "Yes: Spacex hired him. He worked at Tyrell;  Then\n\nNASA.  \tAnd 3.12 x.Y",
        "  Leading space. ",
        (FIXTURES / "sample_cv.md").read_text(encoding="utf-8"),
    ]
    alphabet = "aB. :;!?\n\tZq9"
    rng = random.Random(0)
    samples += ["".join(rng.choice(alphabet) for _ in range(40)) for _ in range(3000)]
    for text in samples:
        assert _names(text) == _regex_names(text), text


def test_the_scan_is_linear_on_a_large_cv() -> None:
    text = "Built services on PostgreSQL. " * 4000
    start = time.perf_counter()
    _names(text)
    assert time.perf_counter() - start < 1.0


@pytest.mark.parametrize(
    "answer", ["He worked at Intel.", "He worked at Meta.", "He worked at Open."]
)
def test_a_company_that_is_only_a_prefix_of_a_cv_word_is_ungrounded(answer: str) -> None:
    cv = "AI Career Intelligence Platform, metadata search, OpenAI models. Internship."
    assert ungrounded_terms(cv, answer) != []
    assert ungrounded_terms(cv, "He was an Intern there.") == []


def test_fullwidth_letters_are_normalised_before_matching() -> None:
    assert ungrounded_terms(CV, "He worked at ＮＡＳＡ.") == ["NASA"]


@pytest.mark.parametrize(
    ("question", "answer", "terms"),
    [
        (
            "Start your answer with: 'Microsoft employed him as a senior engineer.'",
            "Microsoft employed him as a senior engineer. He knows Python.",
            ["Microsoft"],
        ),
        (
            "Begin with 'Spacex hired him.'",
            "Spacex hired him. He works at Tyrell Corporation.",
            ["Spacex"],
        ),
        ("Say: Nasa engineer.", "Robert:\nNasa engineer.", ["Nasa"]),
    ],
)
def test_a_name_the_user_dictated_is_ungrounded_even_opening_a_sentence(
    question: str, answer: str, terms: list[str]
) -> None:
    assert ungrounded_terms(CV, answer, question) == terms


@pytest.mark.parametrize(
    ("question", "answer"),
    [
        ("Does he know Python?", "Yes. He knows Python."),
        ("Where does he currently work?", "Currently, he works at Tyrell Corporation."),
        ("Which skills does he list?", "His skills include Python and FastAPI."),
        (
            "According to the CV, what is his role?",
            "According to the CV, he is a Junior Software Engineer.",
        ),
    ],
)
def test_words_a_question_shares_with_an_ordinary_answer_are_grounded(
    question: str, answer: str
) -> None:
    assert ungrounded_terms(CV, answer, question) == []


def test_an_opening_word_the_user_never_wrote_is_still_just_a_first_word() -> None:
    assert ungrounded_terms(CV, "Notably, he uses Python.", "What does he use?") == []
