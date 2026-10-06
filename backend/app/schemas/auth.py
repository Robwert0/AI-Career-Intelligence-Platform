import unicodedata
import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
    TypeAdapter,
    ValidationError,
)


def _within_bcrypt_limit(v: str) -> str:
    if len(v.encode("utf-8")) > 72:
        raise ValueError("password must not exceed 72 bytes when UTF-8 encoded")
    return v


Password = Annotated[str, Field(min_length=8), AfterValidator(_within_bcrypt_limit)]

_EMAIL = TypeAdapter(EmailStr)


def normalize_email(value: str) -> str:
    # The scripts must look accounts up by the same normalized form registration stored.
    try:
        return _EMAIL.validate_python(value)
    except ValidationError as exc:
        error = exc.errors()[0]
        raise ValueError(error.get("ctx", {}).get("reason", error["msg"])) from None


UserRole = Literal["recruiter", "hiring_manager", "engineer", "other"]


def _blank_to_none(v: str | None) -> str | None:
    return v or None


def _no_control_or_format_chars(v: str) -> str:
    # Cf covers bidi overrides and zero-width characters that can disguise a name in the admin list.
    if any(unicodedata.category(ch) in ("Cc", "Cf") for ch in v):
        raise ValueError("company must not contain control or invisible formatting characters")
    return v


Company = Annotated[
    Annotated[
        str,
        StringConstraints(strip_whitespace=True, max_length=100),
        AfterValidator(_no_control_or_format_chars),
    ]
    | None,
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
