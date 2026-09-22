from pydantic import BaseModel, Field


class Source(BaseModel):
    section: str
    content: str


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


class ChatResponse(BaseModel):
    answer: str
    refused: bool
    sources: list[Source]
