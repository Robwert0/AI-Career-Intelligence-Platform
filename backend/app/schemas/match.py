from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.ai.match.schemas import EvidenceKind, JobPosting

JobText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=50, max_length=30_000)]


class JobIntakeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: Annotated[str, Field(max_length=2048)] | None = None
    text: JobText | None = None

    @model_validator(mode="after")
    def _exactly_one_source(self) -> Self:
        if (self.url is None) == (self.text is None):
            raise ValueError("provide exactly one of url or text")
        return self


Recovery = Literal[
    "paste",
    "retry",
    "fix_url",
    "wait",
    "choose_file",
    "paste_cv",
    "fix_github_url",
    "retry_or_continue",
    "edit_job",
]


class JobSubmitted(BaseModel):
    job_id: str


class FailureOut(BaseModel):
    code: str
    message: str
    recovery: Recovery


IntakeStatus = Literal["queued", "running", "done", "failed"]
IntakeStage = Literal["reading", "extracting"]


class JobStatusResponse(BaseModel):
    job_id: str
    status: IntakeStatus
    stage: IntakeStage | None
    error: FailureOut | None
    posting: JobPosting | None
    source_url: str | None
    input_truncated: bool

    @model_validator(mode="after")
    def _status_carries_its_payload(self) -> Self:
        if self.status == "done" and self.posting is None:
            raise ValueError("a done job must carry its posting")
        if self.status == "failed" and self.error is None:
            raise ValueError("a failed job must carry its error")
        return self


SourceName = Literal["cv", "github"]


class AnalysisInput(BaseModel):
    """What the worker needs besides the CV bytes; stored as a blob next to the record."""

    model_config = ConfigDict(extra="forbid")

    posting: JobPosting
    github_url: str | None = None
    cv_provided: bool = False


SourceStatus = Literal["read", "not_provided", "failed", "skipped"]
RequirementStatus = Literal["demonstrated", "partial", "not_demonstrated", "unmet", "not_assessed"]


class MatchConfig(BaseModel):
    max_upload_bytes: int
    cv_text_min_chars: int
    cv_text_max_chars: int


class AnalysisSubmitted(BaseModel):
    analysis_id: str


class Refusal(BaseModel):
    reasons: list[str]
    needed: list[str]


class Summary(BaseModel):
    strongest: list[str] = Field(default_factory=list, max_length=3)
    gaps: list[str] = Field(default_factory=list, max_length=3)


Ratio = Annotated[float, Field(ge=0.0, le=1.0)]
CATEGORY_ORDER = ("required", "preferred", "applied_evidence")


class BreakdownRowOut(BaseModel):
    category: Literal["required", "preferred", "applied_evidence"]
    weight: int = Field(ge=0, le=100)
    effective_weight: float = Field(ge=0.0, le=100.0)
    score: Ratio
    points: float = Field(ge=0.0, le=100.0)


class GitHubCoverage(BaseModel):
    status: SourceStatus
    inspected_repos: int = 0
    public_non_fork_repos: int = 0
    readmes_found: int = 0


class Coverage(BaseModel):
    level: Literal["high", "medium", "low"]
    cv: SourceStatus
    github: GitHubCoverage
    requirements_with_evidence: Ratio
    limitations: list[str]


class EvidenceOut(BaseModel):
    id: str
    source: SourceName
    kind: EvidenceKind
    section_label: str
    text: str
    url: str | None


class RequirementOut(BaseModel):
    id: str
    text: str
    importance: Literal["required", "preferred"]
    status: RequirementStatus
    rationale: str
    hard_gap: bool
    evidence: list[EvidenceOut]

    @model_validator(mode="after")
    def _hard_gap_is_a_required_unmet_item(self) -> Self:
        if self.hard_gap != (self.importance == "required" and self.status == "unmet"):
            raise ValueError("hard_gap is true exactly for a required, unmet requirement")
        return self


class RecommendationOut(BaseModel):
    requirement_id: str
    title: str
    detail: str


class Recommendations(BaseModel):
    immediate: list[RecommendationOut] = Field(default_factory=list)
    longer_term: list[RecommendationOut] = Field(default_factory=list)


class RewriteOut(BaseModel):
    evidence_id: str
    before: str
    after: str
    questions: list[str]


class MatchReport(BaseModel):
    score: int | None = Field(ge=0, le=100)
    refusal: Refusal | None
    summary: Summary
    breakdown: list[BreakdownRowOut]
    coverage: Coverage
    requirements: list[RequirementOut]
    recommendations: Recommendations
    rewrites: list[RewriteOut]
    disclaimer: str
    model: str

    @model_validator(mode="after")
    def _contract_invariants(self) -> Self:
        if (self.score is None) != (self.refusal is not None):
            raise ValueError("a report is either scored or refused, never both or neither")
        if tuple(row.category for row in self.breakdown) != CATEGORY_ORDER:
            raise ValueError("breakdown must hold the 3 categories in contract order")
        if self.refusal is not None and (
            self.requirements
            or self.rewrites
            or self.recommendations.immediate
            or self.recommendations.longer_term
        ):
            raise ValueError("a refusal carries no requirements, advice or rewrites")
        return self


class DecisionOut(BaseModel):
    failed_source: SourceName
    error: FailureOut


AnalysisStatus = Literal["queued", "running", "needs_decision", "done", "failed"]
AnalysisStage = Literal[
    "reading_cv", "reading_github", "matching", "assessing", "scoring", "recommending"
]


class AnalysisStatusResponse(BaseModel):
    analysis_id: str
    status: AnalysisStatus
    stage: AnalysisStage | None
    queue_position: int | None = Field(ge=0)
    error: FailureOut | None
    decision: DecisionOut | None
    report: MatchReport | None

    @model_validator(mode="after")
    def _status_carries_its_payload(self) -> Self:
        # Violating any of these would strand the UI, so they fail loudly (500) instead.
        if (self.status == "done") != (self.report is not None):
            raise ValueError("report is set exactly when the analysis is done")
        if (self.status == "needs_decision") != (self.decision is not None):
            raise ValueError("decision is set exactly when the analysis needs one")
        if (self.status == "failed") != (self.error is not None):
            raise ValueError("error is set exactly when the analysis failed")
        if self.queue_position is not None and self.status != "queued":
            raise ValueError("queue_position is only set while queued")
        return self
