import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field, StringConstraints


def _within_bcrypt_limit(v: str) -> str:
    if len(v.encode("utf-8")) > 72:
        raise ValueError("password must not exceed 72 bytes when UTF-8 encoded")
    return v


Password = Annotated[str, Field(min_length=8), AfterValidator(_within_bcrypt_limit)]


UserRole = Literal["recruiter", "hiring_manager", "engineer", "other"]


def _blank_to_none(v: str | None) -> str | None:
    return v or None


Company = Annotated[
    Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)] | None,
    AfterValidator(_blank_to_none),
]


class UserCreate(BaseModel):
    email: EmailStr
    password: Password
    company: Company = None
    role: UserRole | None = None


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    created_at: datetime
    company: str | None
    role: UserRole | None
    is_admin: bool


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LoginRequest(BaseModel):
    email: EmailStr
    password: Password
