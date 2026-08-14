from pathlib import Path
from typing import Annotated

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


settings = Settings()
