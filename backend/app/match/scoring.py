import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, Literal

Importance = Literal["required", "preferred"]
Status = Literal["demonstrated", "partial", "not_demonstrated", "unmet", "not_assessed"]
Category = Literal["required", "preferred", "applied_evidence"]
RefusalCode = Literal["insufficient_job", "insufficient_evidence", "unrelated_sources"]
CoverageLevel = Literal["high", "medium", "low"]

CREDIT: Final[dict[Status, float]] = {
    "demonstrated": 1.0,
    "partial": 0.5,
    "not_demonstrated": 0.0,
    "unmet": 0.0,
}
WEIGHTS: Final[dict[Category, int]] = {"required": 70, "preferred": 20, "applied_evidence": 10}
APPLIED_KINDS: Final = frozenset({"work", "project", "repo"})
MIN_ASSESSED_REQUIREMENTS: Final = 3
MIN_EVIDENCE_ITEMS: Final = 3


@dataclass(frozen=True, slots=True)
class ScoredRequirement:
    importance: Importance
    status: Status
    evidence_kinds: frozenset[str] = frozenset()

    @property
    def assessed(self) -> bool:
        return self.status != "not_assessed"

    @property
    def credit(self) -> float:
        return CREDIT.get(self.status, 0.0)


@dataclass(frozen=True, slots=True)
class BreakdownRow:
    category: Category
    weight: int
    effective_weight: float
    score: float
    points: float


@dataclass(frozen=True, slots=True)
class Score:
    total: int
    breakdown: tuple[BreakdownRow, ...]
    redistributed: tuple[Category, ...]


def round_half_up(value: float) -> int:
    # round() is banker's rounding: 66.5 would become 66, which a reader would call a bug.
    return math.floor(value + 0.5)


def _mean(values: Sequence[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _applied_share(required: Sequence[ScoredRequirement]) -> float:
    credited = [item for item in required if item.credit > 0]
    if not credited:
        return 0.0
    applied = [item for item in credited if item.evidence_kinds & APPLIED_KINDS]
    return len(applied) / len(credited)


def score(requirements: Sequence[ScoredRequirement]) -> Score:
    assessed = [item for item in requirements if item.assessed]
    required = [item for item in assessed if item.importance == "required"]
    preferred = [item for item in assessed if item.importance == "preferred"]
    if not required:
        raise ValueError("a score needs at least one assessed required requirement")

    raw: dict[Category, float | None] = {
        "required": _mean([item.credit for item in required]),
        "preferred": _mean([item.credit for item in preferred]),
        "applied_evidence": _applied_share(required),
    }
    present = [category for category, value in raw.items() if value is not None]
    scale = 100 / sum(WEIGHTS[category] for category in present)

    rows: list[BreakdownRow] = []
    exact_total = 0.0
    for category, weight in WEIGHTS.items():
        value = raw[category]
        effective = weight * scale if value is not None else 0.0
        points = effective * (value or 0.0)
        exact_total += points
        rows.append(
            BreakdownRow(
                category=category,
                weight=weight,
                effective_weight=round(effective, 1),
                score=round(value or 0.0, 3),
                points=round(points, 1),
            )
        )
    redistributed = tuple(category for category in WEIGHTS if raw[category] is None)
    return Score(
        total=round_half_up(exact_total), breakdown=tuple(rows), redistributed=redistributed
    )


def refusal_reasons(
    requirements: Sequence[ScoredRequirement],
    *,
    evidence_items: int,
    best_similarity: float,
    min_similarity: float,
) -> tuple[RefusalCode, ...]:
    assessed = [item for item in requirements if item.assessed]
    reasons: list[RefusalCode] = []
    if len(assessed) < MIN_ASSESSED_REQUIREMENTS or not any(
        item.importance == "required" for item in assessed
    ):
        reasons.append("insufficient_job")
    if evidence_items < MIN_EVIDENCE_ITEMS:
        reasons.append("insufficient_evidence")
    if best_similarity < min_similarity:
        reasons.append("unrelated_sources")
    return tuple(reasons)


def coverage_level(requirements_with_evidence: float, *, every_source_read: bool) -> CoverageLevel:
    if requirements_with_evidence >= 0.75 and every_source_read:
        return "high"
    if requirements_with_evidence >= 0.4:
        return "medium"
    return "low"
