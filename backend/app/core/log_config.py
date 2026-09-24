import logging.config

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"
QUIET_LOGGERS = ("httpx", "httpcore", "sqlalchemy.engine")


def configure_logging(level: str) -> None:
    logging.config.dictConfig(
        {
            "version": 1,
            # Module loggers are created at import time, before this runs; the default (True)
            # would silently mute every one of them.
            "disable_existing_loggers": False,
            "formatters": {"default": {"format": LOG_FORMAT}},
            "handlers": {
                "stderr": {"class": "logging.StreamHandler", "formatter": "default"},
            },
            "root": {"level": level, "handlers": ["stderr"]},
            # httpx logs full request URLs at INFO (userinfo and query strings included), and
            # sqlalchemy.engine at INFO logs bound parameters: password and token hashes.
            "loggers": {name: {"level": "WARNING"} for name in QUIET_LOGGERS},
        }
    )
