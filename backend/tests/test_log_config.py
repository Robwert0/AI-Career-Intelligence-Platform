import logging
from collections.abc import Iterator

import pytest
from pydantic import ValidationError

from app.core.config import Settings, settings
from app.core.log_config import configure_logging
from app.main import app, lifespan


@pytest.fixture(autouse=True)
def restore_root_logger() -> Iterator[None]:
    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level
    yield
    root.handlers[:] = handlers
    root.setLevel(level)


def _format(level: int, name: str, message: str) -> str:
    [handler] = logging.getLogger().handlers
    assert handler.formatter is not None
    record = logging.LogRecord(name, level, __file__, 1, message, None, None)
    return handler.formatter.format(record)


def test_info_lines_reach_a_handler_instead_of_being_dropped() -> None:
    configure_logging("INFO")

    root = logging.getLogger()
    assert root.level == logging.INFO
    assert len(root.handlers) == 1


def test_loggers_created_before_configuration_stay_enabled() -> None:
    early = logging.getLogger("app.ai.created_at_import_time")

    configure_logging("INFO")

    assert not early.disabled
    assert early.isEnabledFor(logging.INFO)


def test_records_carry_a_timestamp_level_and_logger_name() -> None:
    configure_logging("INFO")

    line = _format(logging.ERROR, "app.ai.rag", "chat output rejected user=u-1")

    assert line.split(" ", 2)[0].count("-") == 2
    assert " ERROR app.ai.rag chat output rejected user=u-1" in line


def test_the_configured_level_filters_lower_records() -> None:
    configure_logging("WARNING")

    assert not logging.getLogger("app.ai.rag").isEnabledFor(logging.INFO)


def test_log_level_rejects_an_unknown_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_LEVEL", "VERBOSE")

    with pytest.raises(ValidationError, match="log_level"):
        Settings()


async def test_the_lifespan_configures_logging_from_settings() -> None:
    logging.getLogger().handlers.clear()

    async with lifespan(app):
        assert logging.getLogger().level == logging.getLevelNamesMapping()[settings.log_level]
        assert len(logging.getLogger().handlers) == 1
