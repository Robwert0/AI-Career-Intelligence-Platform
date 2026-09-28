from typing import Any

import pytest
from pydantic import ValidationError

from app.ai.match.schemas import EvidenceItem


def item(**overrides: Any) -> dict[str, Any]:
    return {
        "id": "cv:experience:0",
        "sources": ("cv",),
        "kind": "work",
        "section_label": "Experience · Acme",
        "text": "Built Go services.",
    } | overrides


def test_a_valid_item_is_accepted() -> None:
    EvidenceItem.model_validate(item())


def test_sources_may_not_repeat() -> None:
    with pytest.raises(ValidationError):
        EvidenceItem.model_validate(item(sources=("cv", "cv")))


@pytest.mark.parametrize(
    ("id_", "sources", "kind"),
    [
        ("gh:repo:jarvis", ("cv",), "repo"),
        ("gh:repo:jarvis", ("github",), "work"),
        ("gh:profile", ("cv",), "profile"),
        ("gh:profile", ("github",), "repo"),
        ("cv:experience:0", ("github",), "work"),
    ],
)
def test_the_id_prefix_must_match_its_sources_and_kind(
    id_: str, sources: tuple[str, ...], kind: str
) -> None:
    with pytest.raises(ValidationError):
        EvidenceItem.model_validate(item(id=id_, sources=sources, kind=kind))


def test_a_merged_project_may_carry_both_sources() -> None:
    EvidenceItem.model_validate(
        item(
            id="cv:project:0",
            sources=("cv", "github"),
            kind="project",
            url="https://github.com/octo-dev/jarvis",
        )
    )


def test_url_is_not_allowed_for_a_plain_work_item() -> None:
    with pytest.raises(ValidationError):
        EvidenceItem.model_validate(
            item(
                id="cv:experience:0",
                sources=("cv",),
                kind="work",
                url="https://github.com/octo-dev/jarvis",
            )
        )


def test_a_repo_item_may_carry_its_url() -> None:
    EvidenceItem.model_validate(
        item(
            id="gh:repo:jarvis",
            sources=("github",),
            kind="repo",
            section_label="GitHub · jarvis",
            url="https://github.com/octo-dev/jarvis",
        )
    )


def test_a_profile_item_is_github_only() -> None:
    EvidenceItem.model_validate(
        item(id="gh:profile", sources=("github",), kind="profile", section_label="GitHub · profile")
    )
