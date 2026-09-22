import pytest
from pydantic import ValidationError

from app.core.config import Settings


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


def test_cv_document_id_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CV_DOCUMENT_ID", raising=False)

    with pytest.raises(ValidationError, match="cv_document_id"):
        Settings(_env_file=None)


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
