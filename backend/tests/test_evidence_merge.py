from typing import Any

from app.ai.match.dedup import merge_evidence
from app.ai.match.evidence_extract import github_evidence
from app.ai.match.schemas import EvidenceItem
from app.integrations.github import GitHubProfile, GitHubRepo, GitHubSnapshot


def gh_repo(name: str, **overrides: Any) -> GitHubRepo:
    fields: dict[str, Any] = {
        "name": name,
        "url": f"https://github.com/octo-dev/{name}",
        "description": "A voice assistant",
        "languages": {"Python": 900, "Shell": 100},
        "topics": ["llm", "speech"],
        "stars": 12,
        "pushed_at": "2026-08-30T10:00:00Z",
        "readme": "# Jarvis\n![ci](https://img.shields.io/b)\nRuns a [local LLM](http://x).",
    }
    return GitHubRepo.model_validate(fields | overrides)


def snapshot(*repos: GitHubRepo, **profile: Any) -> GitHubSnapshot:
    return GitHubSnapshot(
        profile=GitHubProfile.model_validate(
            {"login": "octo-dev", "name": "Octo Dev", "bio": "Backend engineer", "public_repos": 7}
            | profile
        ),
        repos=list(repos),
        candidate_repos=len(repos),
        fetched_at=0.0,
    )


def cv_item(id: str, kind: str, name: str | None, **extra: Any) -> EvidenceItem:
    return EvidenceItem.model_validate(
        {
            "id": id,
            "sources": ("cv",),
            "kind": kind,
            "section_label": f"Projects · {name}",
            "name": name,
            "text": f"{name}: built in Python.",
        }
        | extra
    )


# --- GitHub evidence --------------------------------------------------------------------


def test_each_repository_becomes_one_deterministic_item() -> None:
    items = github_evidence(snapshot(gh_repo("Jarvis")))

    repo = items[1]
    assert (repo.id, repo.kind, repo.sources) == ("gh:repo:jarvis", "repo", ("github",))
    assert repo.url == "https://github.com/octo-dev/Jarvis"
    assert repo.section_label == "GitHub · Jarvis"
    assert "Python 90%, Shell 10%" in repo.text
    assert "Topics: llm, speech" in repo.text
    assert "Last pushed 2026-08" in repo.text
    assert repo.text.endswith("README: Jarvis Runs a local LLM")
    assert "shields.io" not in repo.text
    assert github_evidence(snapshot(gh_repo("Jarvis"))) == items


def test_a_description_ending_in_a_period_is_not_doubled() -> None:
    items = github_evidence(snapshot(gh_repo("jarvis", description="A voice assistant."), bio=None))

    assert "assistant.." not in items[0].text


def test_languages_under_one_percent_are_left_out() -> None:
    repo = gh_repo("jarvis", languages={"Python": 9950, "Mako": 50})

    items = github_evidence(snapshot(repo, bio=None))

    assert "Languages: Python 100%." in items[0].text
    assert "Mako" not in items[0].text


def test_the_profile_item_comes_first_and_carries_no_url() -> None:
    items = github_evidence(snapshot(gh_repo("jarvis"), company="Acme"))

    profile = items[0]
    assert (profile.id, profile.kind, profile.url) == ("gh:profile", "profile", None)
    assert "Backend engineer" in profile.text
    assert "Company: Acme" in profile.text


def test_a_bio_ending_in_a_period_is_not_doubled() -> None:
    items = github_evidence(snapshot(bio="Backend engineer.", company=None))

    assert items[0].text == "GitHub profile of Octo Dev. Backend engineer. 7 public repositories."


def test_a_profile_with_nothing_to_say_yields_no_profile_item() -> None:
    items = github_evidence(snapshot(gh_repo("jarvis"), bio=None, company=None))

    assert [item.id for item in items] == ["gh:repo:jarvis"]


def test_a_sensitive_bio_is_scrubbed() -> None:
    items = github_evidence(snapshot(bio="Proud dad. Religion: none. Rust and Go.", company=None))

    assert "Religion" not in items[0].text
    assert "Rust and Go" in items[0].text


def test_repo_text_is_capped_at_600_characters() -> None:
    items = github_evidence(snapshot(gh_repo("big", readme="word " * 2000), bio=None))

    assert len(items[0].text) <= 600
    assert items[0].text.endswith("…")


# --- merging --------------------------------------------------------------------------


def test_a_cv_project_and_its_repo_merge_into_one_cv_item() -> None:
    cv = (cv_item("cv:project:0", "project", "Jarvis"),)
    github = github_evidence(snapshot(gh_repo("jarvis"), bio=None))

    merged = merge_evidence(cv, github)

    assert [item.id for item in merged] == ["cv:project:0"]
    item = merged[0]
    assert item.sources == ("cv", "github")
    assert item.url == "https://github.com/octo-dev/jarvis"
    assert item.text.startswith("Jarvis: built in Python. GitHub: jarvis: A voice assistant")
    assert len(item.text) <= 600


def test_names_match_ignoring_case_and_punctuation() -> None:
    cv = (cv_item("cv:project:0", "project", "Jarvis-AI"),)
    github = github_evidence(snapshot(gh_repo("jarvis_ai"), bio=None))

    assert [item.id for item in merge_evidence(cv, github)] == ["cv:project:0"]


def test_a_repo_link_in_the_cv_merges_even_when_names_differ() -> None:
    cv = (
        cv_item(
            "cv:project:0",
            "project",
            "Voice assistant",
            repo_links=("https://github.com/octo-dev/jarvis",),
        ),
    )
    github = github_evidence(snapshot(gh_repo("Jarvis"), bio=None))

    merged = merge_evidence(cv, github)

    assert [(item.id, item.sources) for item in merged] == [("cv:project:0", ("cv", "github"))]


def test_unrelated_items_are_all_kept_cv_first() -> None:
    cv = (
        cv_item("cv:experience:0", "work", "Acme"),
        cv_item("cv:project:0", "project", "Ledger"),
    )
    github = github_evidence(snapshot(gh_repo("jarvis")))

    merged = merge_evidence(cv, github)

    assert [item.id for item in merged] == [
        "cv:experience:0",
        "cv:project:0",
        "gh:profile",
        "gh:repo:jarvis",
    ]


def test_a_job_never_merges_with_a_repo_of_the_same_name() -> None:
    cv = (cv_item("cv:experience:0", "work", "Jarvis"),)
    github = github_evidence(snapshot(gh_repo("jarvis"), bio=None))

    assert len(merge_evidence(cv, github)) == 2


def test_a_repo_merges_into_at_most_one_project() -> None:
    cv = (
        cv_item("cv:project:0", "project", "Jarvis"),
        cv_item("cv:project:1", "project", "jarvis"),
    )
    github = github_evidence(snapshot(gh_repo("jarvis"), bio=None))

    merged = merge_evidence(cv, github)

    assert [item.sources for item in merged] == [("cv", "github"), ("cv",)]


def test_very_short_names_never_merge_by_name() -> None:
    cv = (cv_item("cv:project:0", "project", "AI"),)
    github = github_evidence(snapshot(gh_repo("ai"), bio=None))

    assert len(merge_evidence(cv, github)) == 2


def test_no_github_leaves_the_cv_items_untouched() -> None:
    cv = (cv_item("cv:project:0", "project", "Jarvis"),)

    assert merge_evidence(cv, ()) == cv


def test_a_descriptive_suffix_after_a_spaced_dash_still_matches() -> None:
    cv = (cv_item("cv:project:0", "project", "Jarvis — Voice-Controlled AI Assistant"),)
    github = github_evidence(snapshot(gh_repo("jarvis"), bio=None))

    assert [item.sources for item in merge_evidence(cv, github)] == [("cv", "github")]


def test_a_hyphenated_name_is_not_cut_at_its_hyphen() -> None:
    cv = (cv_item("cv:project:0", "project", "Real-Time Attendance"),)
    github = github_evidence(snapshot(gh_repo("real"), bio=None))

    assert len(merge_evidence(cv, github)) == 2
