from dataclasses import dataclass
from typing import Literal

from app.ai.match.schemas import JobPosting, Requirement

Importance = Literal["required", "preferred"]


@dataclass(frozen=True, slots=True)
class RequirementRef:
    id: str
    text: str
    importance: Importance
    sensitive: bool


def requirement_refs(posting: JobPosting) -> tuple[RequirementRef, ...]:
    """Required first, then preferred, each in posting order: the report's order too."""
    groups: tuple[tuple[Importance, list[Requirement]], ...] = (
        ("required", posting.required),
        ("preferred", posting.preferred),
    )
    return tuple(
        RequirementRef(
            id=f"req:{importance}:{index}",
            text=requirement.text,
            importance=importance,
            sensitive=requirement.sensitive,
        )
        for importance, requirements in groups
        for index, requirement in enumerate(requirements)
    )
