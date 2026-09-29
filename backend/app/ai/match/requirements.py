import re
from dataclasses import dataclass
from typing import Literal

from app.ai.match.schemas import JobPosting, Requirement
from app.ai.match.scrub import mentions_sensitive

Importance = Literal["required", "preferred"]


# Age bounds ("under 35") and gender restrictions. Kept out of the evidence scrub on purpose:
# there "under 50 ms" is a result; in a posting's requirement a bound like this means an age.
_REQUIREMENT_ONLY = re.compile(
    r"\b(?:under|below|over|above|younger\s+than|older\s+than)\s+(?:the\s+age\s+of\s+)?"
    r"\d{2}\b(?!\s*(?:\+|%|ms\b|years?\s+(?:of|in|working|experience)|hours?|users|people"
    r"|employees|engineers|countries|languages|projects|customers|million|k\b|m\b))"
    r"|\baged?\s+(?:between\s+)?\d{2}"
    r"|\b\d{2}\s*(?:-|–|and|to)\s*\d{2}\s+years?\s+(?:old|of\s+age)"
    r"|\b(?:male|female|men|women)\s+(?:candidates?|applicants?|only)\b",
    re.IGNORECASE,
)


def requirement_is_sensitive(text: str) -> bool:
    return mentions_sensitive(text) or bool(_REQUIREMENT_ONLY.search(text))


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
            # The client's flag can be stale or forged, so the server re-checks the text itself.
            sensitive=requirement.sensitive or requirement_is_sensitive(requirement.text),
        )
        for importance, requirements in groups
        for index, requirement in enumerate(requirements)
    )
