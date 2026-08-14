from pathlib import Path
from typing import Annotated
from urllib.parse import urlsplit

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT_DIR / ".env", extra="ignore")

    env: str = "development"
    database_url: str
    redis_url: str
    secret_key: Annotated[str, Field(min_length=32)]
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7
    # NoDecode: without it the env source JSON-decodes this and raises before the validator runs.
    cors_allowed_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("cors_allowed_origins", mode="after")
    @classmethod
    def _reject_unusable_origins(cls, origins: list[str]) -> list[str]:
        for origin in origins:
            # "*" is not merely illegal with credentials: Starlette reflects the requesting
            # origin instead of refusing, so one stray "*" admits everyone with credentials.
            if origin == "*":
                raise ValueError("wildcard origin admits every site with credentials")
            parsed = urlsplit(origin)
            if (
                origin != origin.lower()
                or parsed.scheme not in ("http", "https")
                or not parsed.netloc
                or parsed.path
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError(
                    f"{origin!r} must be a bare lowercase scheme://host[:port] "
                    "with no trailing slash — a browser Origin never matches otherwise"
                )
        return origins


settings = Settings()
