from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.ai.match.schemas import JobPosting

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
