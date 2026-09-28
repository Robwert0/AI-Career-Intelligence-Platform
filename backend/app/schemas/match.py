from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

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
