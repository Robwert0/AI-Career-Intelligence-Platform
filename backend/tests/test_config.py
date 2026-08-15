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
