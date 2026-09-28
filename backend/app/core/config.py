import uuid
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[3]

# Stage bounds that are fixed in code, not settings; test_config pins each to its source.
PARSE_BUDGET_SECONDS = 30
GITHUB_BUDGET_SECONDS = 20
EMBED_BUDGET_SECONDS = 60
OVERHEAD_BUDGET_SECONDS = 30
ANALYSIS_FIXED_BUDGET_SECONDS = (
    PARSE_BUDGET_SECONDS + GITHUB_BUDGET_SECONDS + EMBED_BUDGET_SECONDS + OVERHEAD_BUDGET_SECONDS
)
MAX_ASSESS_CALLS = 8


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
    celery_broker_url: str = "redis://localhost:6379/1"
    job_ttl_seconds: int = Field(default=3600, ge=60)
    job_soft_time_limit_seconds: int = Field(default=300, ge=10)
    generation_context_tokens: int = Field(default=16384, ge=8192)
    job_extract_generation_timeout_seconds: int = Field(default=120, ge=10)
    job_queue_stale_seconds: int = Field(default=900, ge=60)
    max_upload_mb: int = Field(default=5, ge=1, le=20)
    github_token: SecretStr | None = None
    github_cache_ttl_seconds: int = Field(default=3600, ge=60)
    evidence_extract_generation_timeout_seconds: int = Field(default=150, ge=10)
    match_cv_ttl_seconds: int = Field(default=900, ge=60)
    match_preselect_top_k: int = Field(default=8, ge=1, le=20)
    # No default on purpose: the refusal gate is measured by `scripts/eval_match.py calibrate`.
    match_preselect_min_similarity: float = Field(ge=-1.0, le=1.0)
    match_assess_generation_timeout_seconds: int = Field(default=60, ge=10)
    match_recommend_generation_timeout_seconds: int = Field(default=90, ge=10)
    match_analysis_soft_time_limit_seconds: int = Field(default=1800, ge=60)

    @property
    def match_analysis_hard_time_limit_seconds(self) -> int:
        return self.match_analysis_soft_time_limit_seconds + 30

    @property
    def match_analysis_budget_seconds(self) -> int:
        """Worst case for one run of run_analysis: every model call used twice."""
        return (
            ANALYSIS_FIXED_BUDGET_SECONDS
            + 2 * self.evidence_extract_generation_timeout_seconds
            + MAX_ASSESS_CALLS * 2 * self.match_assess_generation_timeout_seconds
            + 2 * self.match_recommend_generation_timeout_seconds
        )

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @field_validator("github_token", mode="before")
    @classmethod
    def _blank_token_is_none(cls, value: object) -> object:
        # GITHUB_TOKEN= in .env must mean "no token", not a Bearer header with an empty secret.
        return None if isinstance(value, str) and not value.strip() else value

    @property
    def job_hard_time_limit_seconds(self) -> int:
        return self.job_soft_time_limit_seconds + 30

    @model_validator(mode="after")
    def _extraction_fits_the_soft_time_limit(self) -> Settings:
        # Two attempts plus the 15s fetch budget must finish before Celery's soft limit fires.
        if 2 * self.job_extract_generation_timeout_seconds + 15 >= self.job_soft_time_limit_seconds:
            raise ValueError(
                "two extraction attempts plus the fetch budget exceed the soft time limit"
            )
        return self

    @model_validator(mode="after")
    def _analysis_fits_its_limits(self) -> Settings:
        if self.match_analysis_budget_seconds >= self.match_analysis_soft_time_limit_seconds:
            raise ValueError(
                f"the analysis worst case ({self.match_analysis_budget_seconds}s) must fit inside "
                "match_analysis_soft_time_limit_seconds"
            )
        # A queued-then-running analysis must finish before its record expires.
        if (
            self.job_queue_stale_seconds + self.match_analysis_hard_time_limit_seconds
            > self.job_ttl_seconds
        ):
            raise ValueError("job_ttl_seconds is too short for a queued analysis to finish")
        return self

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
