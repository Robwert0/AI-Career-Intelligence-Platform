from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

Line = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Company = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class Requirement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: Line
    sensitive: bool


class JobPosting(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Title
    company: Company | None = None
    responsibilities: list[Line] = Field(default_factory=list, max_length=40)
    required: list[Requirement] = Field(default_factory=list, max_length=40)
    preferred: list[Requirement] = Field(default_factory=list, max_length=40)


class ExtractedJob(JobPosting):
    is_job_posting: bool


EvidenceSource = Literal["cv", "github"]
EvidenceKind = Literal[
    "work", "project", "repo", "skill_list", "education", "accomplishment", "profile"
]
CvEntryKind = Literal["work", "project", "skill_list", "education", "accomplishment"]
EvidenceId = Annotated[
    str,
    StringConstraints(
        pattern=(
            r"^(?:gh:profile|gh:repo:[a-z0-9._-]{1,100}"
            r"|cv:(?:experience|project|skills|education|accomplishment):\d{1,3})$"
        )
    ),
]
Label = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
EvidenceText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=600)
]
_REPO_URL = r"^https://github\.com/[A-Za-z0-9-]{1,39}/[A-Za-z0-9._-]{1,100}$"
RepoLink = Annotated[str, StringConstraints(pattern=_REPO_URL)]


class EvidenceItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: EvidenceId
    sources: tuple[EvidenceSource, ...] = Field(min_length=1, max_length=2)
    kind: EvidenceKind
    section_label: Label
    name: Label | None = None
    text: EvidenceText
    url: RepoLink | None = None
    repo_links: tuple[RepoLink, ...] = ()

    @model_validator(mode="after")
    def _id_matches_its_sources_and_kind(self) -> Self:
        if len(set(self.sources)) != len(self.sources):
            raise ValueError("sources must not repeat")
        if self.id == "gh:profile":
            if self.kind != "profile" or self.sources != ("github",):
                raise ValueError("gh:profile must be kind=profile with sources=(github,)")
        elif self.id.startswith("gh:repo:"):
            if self.kind != "repo" or "github" not in self.sources:
                raise ValueError("a gh:repo: id must be kind=repo with github in sources")
        elif self.id.startswith("cv:") and "cv" not in self.sources:
            raise ValueError("a cv: id must have cv in sources")
        if self.url is not None and self.kind not in ("repo", "project"):
            # A bare GitHub repo item (kind=repo) carries its own url; a CV project merged with
            # one (kind=project, dedup.py) keeps it too. No other kind ever has a repo url.
            raise ValueError("url is only allowed for kind=repo or a merged kind=project")
        return self


def _clipped(limit: int) -> BeforeValidator:
    # The model is told the limits; a reply that overshoots is cut, not failed and retried.
    return BeforeValidator(lambda value: value[:limit] if isinstance(value, str) else value)


class CvEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: CvEntryKind
    section_label: Annotated[str, _clipped(120)]
    text: Annotated[str, _clipped(600)]
    links: list[str] = Field(default_factory=list)


class ExtractedCv(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_cv: bool
    items: list[CvEntry] = Field(default_factory=list)
