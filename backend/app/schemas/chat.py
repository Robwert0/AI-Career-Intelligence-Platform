from typing import Final, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_MESSAGE_CHARS: Final = 2000
# Three exchanges: enough to resolve "that" or "there", small enough that history can never
# crowd the CV extracts out of the model's context.
MAX_HISTORY_MESSAGES: Final = 6
MAX_HISTORY_MESSAGE_CHARS: Final = 2000
MAX_HISTORY_CHARS: Final = 6000


class Source(BaseModel):
    section: str
    content: str


class ChatTurn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=MAX_HISTORY_MESSAGE_CHARS)


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)
    history: list[ChatTurn] = Field(default_factory=list, max_length=MAX_HISTORY_MESSAGES)

    @model_validator(mode="after")
    def _history_is_completed_exchanges(self) -> Self:
        # user/assistant pairs only, oldest first: the current question is never also the last
        # history entry, and an unanswered or failed question is never sent as context.
        roles = [turn.role for turn in self.history]
        if roles != ["user", "assistant"] * (len(roles) // 2) or len(roles) % 2:
            raise ValueError("history must be completed user/assistant exchanges, oldest first")
        if any(not turn.content.strip() for turn in self.history):
            raise ValueError("history messages must not be blank")
        if sum(len(turn.content) for turn in self.history) > MAX_HISTORY_CHARS:
            raise ValueError(f"history must total at most {MAX_HISTORY_CHARS} characters")
        return self


class ChatResponse(BaseModel):
    answer: str
    refused: bool
    sources: list[Source]
