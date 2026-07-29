from pathlib import Path
from typing import Annotated

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT_DIR / ".env", extra="ignore")

    env: str = "development"
    database_url: str
    redis_url: str
    secret_key: Annotated[str, Field(min_length=32)]
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7


settings = Settings()
