from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

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
