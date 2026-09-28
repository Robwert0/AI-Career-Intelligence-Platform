from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.ai.match.schemas import JobPosting
from app.core.job_store import JobStatus

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


Recovery = Literal["paste", "retry", "fix_url", "wait"]


class JobSubmitted(BaseModel):
    job_id: str


class FailureOut(BaseModel):
    code: str
    message: str
    recovery: Recovery


class JobStatusResponse(BaseModel):
    job_id: str
    status: JobStatus
    stage: str | None
    error: FailureOut | None
    posting: JobPosting | None
    source_url: str | None
    input_truncated: bool
