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
