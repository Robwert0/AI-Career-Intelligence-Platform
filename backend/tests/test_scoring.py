import random

import pytest

from app.match.scoring import (
    CREDIT,
    BreakdownRow,
    ScoredRequirement,
    Status,
    coverage_level,
    refusal_reasons,
    round_half_up,
    score,
)

WORK = frozenset({"work"})
SKILLS = frozenset({"skill_list"})


def req(status: Status, kinds: frozenset[str] = WORK) -> ScoredRequirement:
    return ScoredRequirement(
        "required", status, kinds if status in ("demonstrated", "partial") else frozenset()
    )


def pref(status: Status, kinds: frozenset[str] = WORK) -> ScoredRequirement:
    return ScoredRequirement(
        "preferred", status, kinds if status in ("demonstrated", "partial") else frozenset()
    )


def row(result_rows: tuple[BreakdownRow, ...], category: str) -> BreakdownRow:
    return next(r for r in result_rows if r.category == category)


def test_the_spec_worked_example_scores_67() -> None:
    requirements = [
        req("demonstrated"),
        req("demonstrated"),
        req("demonstrated"),
        req("demonstrated", SKILLS),
        req("partial"),
        req("not_demonstrated"),
        pref("demonstrated"),
        pref("not_demonstrated"),
        pref("not_demonstrated"),
    ]

    result = score(requirements)

    assert result.total == 67
    assert [r.category for r in result.breakdown] == ["required", "preferred", "applied_evidence"]
    assert (row(result.breakdown, "required").score, row(result.breakdown, "required").points) == (
        0.75,
        52.5,
    )
    assert (
        row(result.breakdown, "preferred").score,
        row(result.breakdown, "preferred").points,
    ) == (0.333, 6.7)
    assert (
        row(result.breakdown, "applied_evidence").score,
        row(result.breakdown, "applied_evidence").points,
    ) == (0.8, 8.0)
    assert result.redistributed == ()


def test_no_preferred_items_redistributes_their_weight() -> None:
    result = score([req("demonstrated"), req("demonstrated"), req("demonstrated")])

    assert result.total == 100
    assert result.redistributed == ("preferred",)
    assert row(result.breakdown, "required").effective_weight == 87.5
    assert row(result.breakdown, "applied_evidence").effective_weight == 12.5
    assert row(result.breakdown, "preferred").effective_weight == 0.0


def test_not_assessed_items_are_excluded_everywhere() -> None:
    base = [req("demonstrated"), req("partial"), pref("demonstrated")]
    with_sensitive = [*base, req("not_assessed"), pref("not_assessed")]

    assert score(with_sensitive) == score(base)


def test_nothing_credited_scores_zero_applied_evidence() -> None:
    result = score([req("not_demonstrated"), req("unmet"), pref("not_demonstrated")])

    assert result.total == 0
    assert row(result.breakdown, "applied_evidence").score == 0.0


def test_skill_lists_alone_are_not_applied_evidence() -> None:
    result = score(
        [req("demonstrated", SKILLS), req("demonstrated", frozenset({"skill_list", "education"}))]
    )

    assert row(result.breakdown, "applied_evidence").score == 0.0


def test_a_repo_counts_as_applied_evidence() -> None:
    result = score([req("demonstrated", frozenset({"repo", "skill_list"}))])

    assert row(result.breakdown, "applied_evidence").score == 1.0


def test_preferred_items_never_move_the_applied_share() -> None:
    required = [req("demonstrated"), req("demonstrated", SKILLS)]

    a = score([*required, pref("demonstrated", SKILLS)])
    b = score([*required, pref("demonstrated")])

    assert (
        row(a.breakdown, "applied_evidence").score
        == row(b.breakdown, "applied_evidence").score
        == 0.5
    )


def test_a_score_needs_an_assessed_required_item() -> None:
    with pytest.raises(ValueError):
        score([pref("demonstrated"), req("not_assessed")])


@pytest.mark.parametrize(("value", "expected"), [(66.5, 67), (67.49, 67), (0.5, 1), (99.5, 100)])
def test_totals_round_half_up(value: float, expected: int) -> None:
    assert round_half_up(value) == expected


STATUSES: list[Status] = ["unmet", "not_demonstrated", "partial", "demonstrated"]


def _random_case(rng: random.Random) -> list[ScoredRequirement]:
    items = [
        ScoredRequirement(
            rng.choice(["required", "preferred"]),
            rng.choice([*STATUSES, "not_assessed"]),
            frozenset(
                rng.sample(
                    ["work", "project", "repo", "skill_list", "education", "profile"],
                    rng.randint(1, 2),
                )
            ),
        )
        for _ in range(rng.randint(1, 12))
    ]
    items.append(ScoredRequirement("required", rng.choice(STATUSES), WORK))
    return items


def test_properties_hold_on_random_assessments() -> None:
    rng = random.Random(0)
    for _ in range(2000):
        result = score(_random_case(rng))
        assert 0 <= result.total <= 100
        assert abs(sum(r.points for r in result.breakdown) - result.total) <= 0.5 + 0.15
        assert abs(sum(r.effective_weight for r in result.breakdown) - 100) <= 0.15


def _upgrades(status: Status) -> list[Status]:
    return STATUSES[STATUSES.index(status) + 1 :] if status in STATUSES else []


def test_upgrading_a_status_never_lowers_the_total_unless_it_dilutes_applied_evidence() -> None:
    rng = random.Random(1)
    for _ in range(2000):
        items = _random_case(rng)
        before = score(items).total
        index = rng.randrange(len(items))
        item = items[index]
        for better in _upgrades(item.status):
            upgraded = ScoredRequirement(item.importance, better, item.evidence_kinds)
            after = score([*items[:index], upgraded, *items[index + 1 :]]).total
            dilutes = (
                item.importance == "required"
                and CREDIT[item.status] == 0
                and not item.evidence_kinds & {"work", "project", "repo"}
            )
            if not dilutes:
                assert after >= before, (items, index, better)


def test_crediting_a_skill_list_only_item_can_dilute_applied_evidence() -> None:
    required = [req("demonstrated"), *[req("not_demonstrated") for _ in range(19)]]
    before = score(required).total

    upgraded = [required[0], req("partial", SKILLS), *required[2:]]

    assert score(upgraded).total < before


def test_every_refusal_condition_is_reported() -> None:
    two_items = [req("demonstrated"), pref("demonstrated")]

    assert refusal_reasons(
        two_items, evidence_items=2, best_similarity=0.1, min_similarity=0.5
    ) == (
        "insufficient_job",
        "insufficient_evidence",
        "unrelated_sources",
    )


def test_no_assessed_required_item_is_an_insufficient_job() -> None:
    items = [pref("demonstrated"), pref("partial"), pref("unmet"), req("not_assessed")]

    assert refusal_reasons(items, evidence_items=9, best_similarity=0.9, min_similarity=0.5) == (
        "insufficient_job",
    )


def test_sensitive_items_do_not_count_towards_the_minimum() -> None:
    items = [req("demonstrated"), req("partial"), req("not_assessed")]

    assert "insufficient_job" in refusal_reasons(
        items, evidence_items=9, best_similarity=0.9, min_similarity=0.5
    )


def test_a_sufficient_analysis_is_not_refused() -> None:
    items = [req("demonstrated"), req("partial"), pref("unmet")]

    assert refusal_reasons(items, evidence_items=3, best_similarity=0.5, min_similarity=0.5) == ()


@pytest.mark.parametrize(
    ("share", "read", "level"),
    [
        (0.75, True, "high"),
        (0.75, False, "medium"),
        (0.4, True, "medium"),
        (0.39, True, "low"),
        (1.0, False, "medium"),
    ],
)
def test_coverage_levels(share: float, read: bool, level: str) -> None:
    assert coverage_level(share, every_source_read=read) == level
