import inspect
import os
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core import config
from app.core.config import Settings
from app.integrations.doc_sandbox import PARSE_TIMEOUT_SECONDS
from app.integrations.github import GitHubClient


def test_short_secret_key_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SECRET_KEY", "change-me-in-prod")

    with pytest.raises(ValidationError, match="secret_key"):
        Settings()


def test_empty_secret_key_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SECRET_KEY", "")

    with pytest.raises(ValidationError, match="secret_key"):
        Settings()


def test_long_secret_key_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SECRET_KEY", "a" * 64)

    assert Settings().secret_key == "a" * 64


def test_cors_origins_default_to_local_dev(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)

    assert Settings(_env_file=None).cors_allowed_origins == ["http://localhost:3000"]


def test_cors_origins_splits_a_comma_separated_env_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://app.example.com, http://localhost:3000")

    assert Settings().cors_allowed_origins == [
        "https://app.example.com",
        "http://localhost:3000",
    ]


def test_cors_origins_accepts_a_single_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://only.example.com")

    assert Settings().cors_allowed_origins == ["https://only.example.com"]


def test_cors_origins_tolerates_a_trailing_comma(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://a.example.com,")

    assert Settings().cors_allowed_origins == ["https://a.example.com"]


def test_cors_origins_reject_an_empty_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "")

    with pytest.raises(ValidationError, match="cors_allowed_origins"):
        Settings()


def test_cors_origins_reject_a_value_of_only_separators(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", " , , ")

    with pytest.raises(ValidationError, match="cors_allowed_origins"):
        Settings()


def test_cors_origins_reject_a_wildcard(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "*")

    with pytest.raises(ValidationError, match="cors_allowed_origins"):
        Settings()


def test_cors_origins_reject_a_wildcard_hidden_among_valid_ones(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://app.example.com,*")

    with pytest.raises(ValidationError, match="cors_allowed_origins"):
        Settings()


def test_cors_origins_reject_a_trailing_slash(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://app.example.com/")

    with pytest.raises(ValidationError, match="cors_allowed_origins"):
        Settings()


def test_cors_origins_reject_a_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://app.example.com/app")

    with pytest.raises(ValidationError, match="cors_allowed_origins"):
        Settings()


def test_cors_origins_reject_a_non_lowercase_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "HTTPS://App.Example.COM")

    with pytest.raises(ValidationError, match="cors_allowed_origins"):
        Settings()


def test_cors_origins_reject_a_non_http_scheme(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "ftp://app.example.com")

    with pytest.raises(ValidationError, match="cors_allowed_origins"):
        Settings()


def test_chat_settings_have_the_documented_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.retrieval_limit == 5
    assert settings.chat_timeout_seconds == 30
    assert settings.chat_max_output_tokens == 512
    assert settings.chat_temperature == 0.0


@pytest.mark.parametrize("value", [None, "", "  "])
def test_settings_load_without_a_cv_document_id(
    monkeypatch: pytest.MonkeyPatch, value: str | None
) -> None:
    # Migrations and ingest load Settings before the id exists; ingest is what prints it.
    if value is None:
        monkeypatch.delenv("CV_DOCUMENT_ID", raising=False)
    else:
        monkeypatch.setenv("CV_DOCUMENT_ID", value)

    assert Settings(_env_file=None).cv_document_id is None


def test_chat_refuses_to_read_a_missing_cv_document_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CV_DOCUMENT_ID", raising=False)

    with pytest.raises(RuntimeError, match="CV_DOCUMENT_ID"):
        Settings(_env_file=None).require_cv_document_id()


def test_require_cv_document_id_returns_the_configured_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CV_DOCUMENT_ID", "44444444-4444-4444-4444-444444444444")

    assert str(Settings(_env_file=None).require_cv_document_id()) == (
        "44444444-4444-4444-4444-444444444444"
    )


def test_migrations_and_ingest_start_without_a_cv_document_id(tmp_path: Path) -> None:
    backend = Path(__file__).resolve().parents[1]
    # PYTHONPATH pins `app` to this checkout; a shared editable venv may point elsewhere.
    env = {**os.environ, "CV_DOCUMENT_ID": "", "PYTHONPATH": str(backend)}

    migrate = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head", "--sql"],
        cwd=backend,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    ingest = subprocess.run(
        [sys.executable, "scripts/ingest_cv.py", str(tmp_path / "absent.pdf")],
        cwd=backend,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert migrate.returncode == 0, migrate.stderr
    assert "CREATE TABLE" in migrate.stdout
    assert ingest.returncode == 2, ingest.stderr
    assert "not a file" in ingest.stderr


def test_cv_document_id_rejects_a_non_uuid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CV_DOCUMENT_ID", "not-a-uuid")

    with pytest.raises(ValidationError, match="cv_document_id"):
        Settings(_env_file=None)


def test_the_chat_timeout_is_shorter_than_the_script_timeout() -> None:
    settings = Settings(_env_file=None)

    assert settings.chat_timeout_seconds < settings.generation_timeout_seconds


def test_the_similarity_threshold_stays_inside_the_cosine_range(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RETRIEVAL_SIMILARITY_THRESHOLD", "1.5")

    with pytest.raises(ValidationError, match="retrieval_similarity_threshold"):
        Settings(_env_file=None)


@pytest.mark.parametrize(
    "url",
    [
        "https://user:pass@ollama.example.com",
        "https://token@ollama.example.com",
        "http://127.0.0.1:11434?key=secret",
        "http://127.0.0.1:11434#frag",
    ],
)
def test_ollama_url_rejects_parts_httpx_would_log(
    monkeypatch: pytest.MonkeyPatch, url: str
) -> None:
    monkeypatch.setenv("OLLAMA_BASE_URL", url)

    with pytest.raises(ValidationError, match="ollama_base_url"):
        Settings()


def test_ollama_url_accepts_a_plain_host(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")

    assert Settings().ollama_base_url == "http://127.0.0.1:11434"


def test_worker_settings_default_to_local_dev(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("CELERY_BROKER_URL", "JOB_TTL_SECONDS", "JOB_SOFT_TIME_LIMIT_SECONDS"):
        monkeypatch.delenv(name, raising=False)

    settings = Settings(_env_file=None)

    # DB 1, not 0: a broker flush must never wipe rate-limit buckets.
    assert settings.celery_broker_url == "redis://localhost:6379/1"
    assert settings.job_ttl_seconds == 3600
    assert settings.job_soft_time_limit_seconds == 300


def test_a_job_ttl_under_a_minute_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JOB_TTL_SECONDS", "59")

    with pytest.raises(ValidationError, match="job_ttl_seconds"):
        Settings()


def test_a_soft_time_limit_under_ten_seconds_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JOB_SOFT_TIME_LIMIT_SECONDS", "9")

    with pytest.raises(ValidationError, match="job_soft_time_limit_seconds"):
        Settings()


def test_generation_and_intake_settings_default(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "GENERATION_CONTEXT_TOKENS",
        "JOB_EXTRACT_GENERATION_TIMEOUT_SECONDS",
        "JOB_QUEUE_STALE_SECONDS",
        "JOB_SOFT_TIME_LIMIT_SECONDS",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = Settings(_env_file=None)

    assert settings.generation_context_tokens == 16384
    assert settings.job_extract_generation_timeout_seconds == 120
    assert settings.job_queue_stale_seconds == 900
    assert settings.job_hard_time_limit_seconds == settings.job_soft_time_limit_seconds + 30


def test_a_context_window_too_small_for_a_posting_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GENERATION_CONTEXT_TOKENS", "4096")

    with pytest.raises(ValidationError, match="generation_context_tokens"):
        Settings()


def test_two_extraction_attempts_must_fit_inside_the_soft_time_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("JOB_SOFT_TIME_LIMIT_SECONDS", "200")
    monkeypatch.setenv("JOB_EXTRACT_GENERATION_TIMEOUT_SECONDS", "100")

    with pytest.raises(ValidationError, match="soft time limit"):
        Settings()


def test_candidate_evidence_settings_default(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "MAX_UPLOAD_MB",
        "GITHUB_TOKEN",
        "GITHUB_CACHE_TTL_SECONDS",
        "EVIDENCE_EXTRACT_GENERATION_TIMEOUT_SECONDS",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = Settings(_env_file=None)

    assert settings.max_upload_mb == 5
    assert settings.max_upload_bytes == 5 * 1024 * 1024
    assert settings.github_token is None
    assert settings.github_cache_ttl_seconds == 3600
    assert settings.evidence_extract_generation_timeout_seconds == 150


def test_max_upload_mb_is_read_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAX_UPLOAD_MB", "3")

    assert Settings().max_upload_bytes == 3 * 1024 * 1024


@pytest.mark.parametrize("value", ["0", "21"])
def test_an_upload_limit_outside_1_to_20_mb_is_rejected(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("MAX_UPLOAD_MB", value)

    with pytest.raises(ValidationError, match="max_upload_mb"):
        Settings()


@pytest.mark.parametrize("value", ["", "   "])
def test_a_blank_github_token_means_no_token(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", value)

    assert Settings().github_token is None


def test_the_github_token_never_appears_in_the_settings_repr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_not_a_real_token_value")

    settings = Settings()

    assert settings.github_token is not None
    assert settings.github_token.get_secret_value() == "ghp_not_a_real_token_value"
    assert "ghp_not_a_real_token_value" not in repr(settings)


def test_analysis_settings_default(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "MATCH_CV_TTL_SECONDS",
        "MATCH_PRESELECT_TOP_K",
        "MATCH_ASSESS_GENERATION_TIMEOUT_SECONDS",
        "MATCH_RECOMMEND_GENERATION_TIMEOUT_SECONDS",
        "MATCH_ANALYSIS_SOFT_TIME_LIMIT_SECONDS",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = Settings(_env_file=None)

    assert settings.match_cv_ttl_seconds == 1200
    assert settings.match_preselect_top_k == 8
    assert settings.match_assess_generation_timeout_seconds == 60
    assert settings.match_recommend_generation_timeout_seconds == 90
    assert settings.match_analysis_soft_time_limit_seconds == 1800
    assert settings.match_analysis_hard_time_limit_seconds == 1830


# Exactly what .github/workflows/ci.yml gives alembic and the worker smoke test.
CI_ENV = {
    "DATABASE_URL": "postgresql+asyncpg://test:test@localhost:5432/postgres",
    "REDIS_URL": "redis://localhost:6379/0",
    "SECRET_KEY": "ci-secret-not-real-000000000000000000",
}


def test_settings_build_from_ci_env_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in list(os.environ):
        if name.startswith(("MATCH_", "JOB_", "CELERY_", "GITHUB_", "MAX_UPLOAD")):
            monkeypatch.delenv(name)
    monkeypatch.delenv("CV_DOCUMENT_ID", raising=False)
    for name, value in CI_ENV.items():
        monkeypatch.setenv(name, value)

    settings = Settings(_env_file=None)

    # The calibrated refusal gates: one per source, each overridable from the environment.
    assert settings.match_preselect_thresholds == {"cv": 0.605, "github": 0.583}


def test_each_refusal_gate_can_be_overridden(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MATCH_PRESELECT_MIN_SIMILARITY", "0.7")
    monkeypatch.setenv("MATCH_PRESELECT_MIN_SIMILARITY_GITHUB", "0.6")

    assert Settings(_env_file=None).match_preselect_thresholds == {"cv": 0.7, "github": 0.6}


def test_the_worst_case_analysis_is_the_documented_sum() -> None:
    settings = Settings(_env_file=None)

    # 30 parse + 2x150 evidence + 20 GitHub + 60 embeddings + 8x2x60 assess + 2x90 recommend + 30.
    assert settings.match_analysis_budget_seconds == 1580


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("MATCH_ASSESS_GENERATION_TIMEOUT_SECONDS", "90"),
        ("EVIDENCE_EXTRACT_GENERATION_TIMEOUT_SECONDS", "400"),
        ("MATCH_ANALYSIS_SOFT_TIME_LIMIT_SECONDS", "1500"),
    ],
)
def test_an_analysis_that_cannot_finish_inside_its_soft_limit_is_rejected(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str
) -> None:
    monkeypatch.setenv(name, value)

    with pytest.raises(ValidationError, match="analysis worst case"):
        Settings(_env_file=None)


def test_a_queued_analysis_must_be_able_to_finish_before_its_record_expires(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("JOB_TTL_SECONDS", "2400")

    with pytest.raises(ValidationError, match="job_ttl_seconds"):
        Settings(_env_file=None)


def test_the_fixed_budget_matches_the_limits_enforced_in_code() -> None:
    total_timeout = inspect.signature(GitHubClient).parameters["total_timeout"].default

    assert config.PARSE_BUDGET_SECONDS == PARSE_TIMEOUT_SECONDS
    assert total_timeout == config.GITHUB_BUDGET_SECONDS


def test_the_assess_call_cap_matches_the_budget() -> None:
    from app.ai.match.assess import MAX_ASSESS_BATCHES

    assert config.MAX_ASSESS_CALLS == MAX_ASSESS_BATCHES


def test_a_cv_blob_outlives_the_longest_a_job_can_wait_queued(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MATCH_CV_TTL_SECONDS", raising=False)
    assert (
        Settings(_env_file=None).match_cv_ttl_seconds
        > Settings(_env_file=None).job_queue_stale_seconds
    )

    monkeypatch.setenv("MATCH_CV_TTL_SECONDS", "900")

    with pytest.raises(ValidationError, match="match_cv_ttl_seconds"):
        Settings(_env_file=None)


def test_the_queued_analysis_cap_has_a_default() -> None:
    assert Settings(_env_file=None).match_max_queued_analyses == 20


def test_the_generation_provider_defaults_to_local_ollama(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("GENERATION_PROVIDER", "OPENAI_API_KEY", "OPENAI_CHAT_MODEL", "OPENAI_BASE_URL"):
        monkeypatch.delenv(name, raising=False)

    settings = Settings(_env_file=None)

    assert settings.generation_provider == "ollama"
    assert settings.openai_api_key is None
    assert settings.openai_chat_model == "gpt-6-luna"
    assert settings.openai_reasoning_effort == "none"
    assert settings.openai_base_url == "https://api.openai.com/v1"


def test_the_openai_provider_without_a_key_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GENERATION_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "  ")

    with pytest.raises(ValidationError, match="OPENAI_API_KEY"):
        Settings(_env_file=None)


def test_the_openai_provider_with_a_key_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GENERATION_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    settings = Settings(_env_file=None)

    assert settings.openai_api_key is not None
    assert settings.openai_api_key.get_secret_value() == "sk-test"


def test_an_unknown_generation_provider_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GENERATION_PROVIDER", "anthropic")

    with pytest.raises(ValidationError, match="generation_provider"):
        Settings(_env_file=None)


def test_an_unknown_reasoning_effort_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_REASONING_EFFORT", "turbo")

    with pytest.raises(ValidationError, match="openai_reasoning_effort"):
        Settings(_env_file=None)


@pytest.mark.parametrize(
    "url", ["https://user:pass@api.openai.com/v1", "https://api.openai.com/v1?key=sk-test"]
)
def test_an_openai_base_url_with_credentials_is_rejected(
    monkeypatch: pytest.MonkeyPatch, url: str
) -> None:
    monkeypatch.setenv("OPENAI_BASE_URL", url)

    with pytest.raises(ValidationError, match="openai_base_url"):
        Settings(_env_file=None)


def test_a_blank_reasoning_effort_means_none_is_sent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_REASONING_EFFORT", "")

    assert Settings(_env_file=None).openai_reasoning_effort is None


@pytest.mark.parametrize(
    "url",
    [
        "http://api.openai.com/v1",
        "http://localhost.evil.example/v1",
        "http://127.0.0.2:8080/v1",
        "ftp://api.openai.com/v1",
        "https:///v1",
    ],
)
def test_an_openai_base_url_that_would_send_the_key_in_cleartext_is_rejected(
    monkeypatch: pytest.MonkeyPatch, url: str
) -> None:
    monkeypatch.setenv("OPENAI_BASE_URL", url)

    with pytest.raises(ValidationError, match="openai_base_url"):
        Settings(_env_file=None)


@pytest.mark.parametrize(
    "url",
    [
        "https://api.openai.com/v1",
        "https://gateway.example.com:8443/openai/v1",
        "http://localhost:8080/v1",
        "http://127.0.0.1:8080/v1",
        "http://[::1]:8080/v1",
    ],
)
def test_an_https_or_loopback_openai_base_url_is_accepted(
    monkeypatch: pytest.MonkeyPatch, url: str
) -> None:
    monkeypatch.setenv("OPENAI_BASE_URL", url)

    assert Settings(_env_file=None).openai_base_url == url


def test_a_loopback_openai_base_url_still_cannot_carry_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_BASE_URL", "http://user:pass@localhost:8080/v1")

    with pytest.raises(ValidationError, match="credentials"):
        Settings(_env_file=None)
