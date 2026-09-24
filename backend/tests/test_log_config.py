import logging
import re
from collections.abc import Iterator

import pytest
from pydantic import ValidationError

from app.core.config import Settings, settings
from app.core.log_config import QUIET_LOGGERS, configure_logging
from app.main import app, lifespan


@pytest.fixture(autouse=True)
def restore_root_logger() -> Iterator[None]:
    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level
    quiet_levels = {name: logging.getLogger(name).level for name in QUIET_LOGGERS}
    yield
    root.handlers[:] = handlers
    root.setLevel(level)
    for name, quiet_level in quiet_levels.items():
        logging.getLogger(name).setLevel(quiet_level)


def test_an_info_line_is_written_to_stderr_with_timestamp_level_and_name(
    capfd: pytest.CaptureFixture[str],
) -> None:
    configure_logging("INFO")

    logging.getLogger("app.ai.rag").info("chat answered user=u-1")

    assert re.fullmatch(
        r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3} INFO app\.ai\.rag chat answered user=u-1\n",
        capfd.readouterr().err,
    )


def test_loggers_created_before_configuration_stay_enabled() -> None:
    early = logging.getLogger("app.ai.created_at_import_time")

    configure_logging("INFO")

    assert not early.disabled
    assert early.isEnabledFor(logging.INFO)


def test_the_configured_level_filters_lower_records() -> None:
    configure_logging("WARNING")

    assert not logging.getLogger("app.ai.rag").isEnabledFor(logging.INFO)


@pytest.mark.parametrize("name", ["httpx", "httpcore", "sqlalchemy.engine"])
def test_loggers_that_leak_urls_or_parameters_stay_at_warning(name: str) -> None:
    configure_logging("DEBUG")

    assert not logging.getLogger(name).isEnabledFor(logging.INFO)


def test_an_httpx_request_url_never_reaches_the_log(capfd: pytest.CaptureFixture[str]) -> None:
    configure_logging("INFO")

    logging.getLogger("httpx").info("HTTP Request: GET http://127.0.0.1/api?key=SECRET")

    assert "SECRET" not in capfd.readouterr().err


def test_log_level_rejects_an_unknown_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_LEVEL", "VERBOSE")

    with pytest.raises(ValidationError, match="log_level"):
        Settings()


async def test_the_lifespan_configures_logging_from_settings(
    logging_config_calls: list[str],
) -> None:
    async with lifespan(app):
        assert logging_config_calls == [settings.log_level]
