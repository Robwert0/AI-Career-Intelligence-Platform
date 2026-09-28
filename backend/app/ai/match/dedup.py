import re

from app.ai.match.evidence_extract import clip_text
from app.ai.match.schemas import EvidenceItem

MIN_NAME_CHARS = 3
_NOT_ALPHANUMERIC = re.compile(r"[^a-z0-9]")
# "Jarvis — Voice-Controlled AI Assistant" is the project "Jarvis": the name ends at a spaced
# dash, a colon, a bracket or a comma. Hyphenated words are never split.
_NAME_END = re.compile(r"\s+[—–-]\s+|[:(,]")


def _normalised(name: str) -> str:
    return _NOT_ALPHANUMERIC.sub("", name.lower())


def _name_keys(name: str | None) -> list[str]:
    if not name:
        return []
    keys = dict.fromkeys((_normalised(name), _normalised(_NAME_END.split(name, maxsplit=1)[0])))
    return [key for key in keys if len(key) >= MIN_NAME_CHARS]


def _matching_repo(
    project: EvidenceItem,
    by_url: dict[str, EvidenceItem],
    by_name: dict[str, EvidenceItem],
    used: set[str],
) -> EvidenceItem | None:
    candidates = [by_url.get(link) for link in project.repo_links]
    candidates += [by_name.get(key) for key in _name_keys(project.name)]
    return next((repo for repo in candidates if repo is not None and repo.id not in used), None)


def merge_evidence(
    cv: tuple[EvidenceItem, ...], github: tuple[EvidenceItem, ...]
) -> tuple[EvidenceItem, ...]:
    """A CV project and the repo it describes become one item, so one piece of work counts once."""
    repos = [item for item in github if item.kind == "repo"]
    by_url = {item.url.lower(): item for item in repos if item.url}
    by_name: dict[str, EvidenceItem] = {}
    for item in repos:
        for key in _name_keys(item.name):
            by_name.setdefault(key, item)

    used: set[str] = set()
    merged: list[EvidenceItem] = []
    for item in cv:
        repo = _matching_repo(item, by_url, by_name, used) if item.kind == "project" else None
        if repo is None:
            merged.append(item)
            continue
        used.add(repo.id)
        merged.append(
            EvidenceItem.model_validate(
                item.model_dump()
                | {
                    "sources": ("cv", "github"),
                    "url": repo.url,
                    "text": clip_text(f"{item.text} GitHub: {repo.text}"),
                }
            )
        )
    merged.extend(item for item in github if item.id not in used)
    return tuple(merged)
