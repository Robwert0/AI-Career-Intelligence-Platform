import uuid
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT_DIR / ".env", extra="ignore")

    env: str = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    database_url: str
    redis_url: str
    secret_key: Annotated[str, Field(min_length=32)]
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_model_revision: str = "5c38ec7c405ec4b44b94cc5a9bb96e735b38267a"
    embedding_dim: int = 384
    cors_allowed_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]
    ollama_base_url: str = "http://127.0.0.1:11434"
    generation_model: str = "qwen3:8b"
    generation_timeout_seconds: int = 180
    generation_connect_timeout_seconds: int = 5
    cv_document_id: uuid.UUID
    retrieval_limit: int = Field(default=5, ge=1, le=20)
    retrieval_similarity_threshold: float = Field(default=0.48, ge=-1.0, le=1.0)
    chat_timeout_seconds: int = Field(default=30, ge=1)
    chat_max_output_tokens: int = Field(default=512, ge=1)
    chat_temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    chat_max_concurrent_generations: int = Field(default=4, ge=1)
    chat_queue_timeout_seconds: float = Field(default=5.0, gt=0.0)

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("ollama_base_url")
    @classmethod
    def _reject_url_credentials(cls, url: str) -> str:
        parsed = urlsplit(url)
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError(
                "must not carry credentials, a query or a fragment: httpx logs request URLs"
            )
        return url

    @field_validator("cors_allowed_origins", mode="after")
    @classmethod
    def _reject_unusable_origins(cls, origins: list[str]) -> list[str]:
        if not origins:
            raise ValueError("at least one origin is required; no browser could reach the API")
        for origin in origins:
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
