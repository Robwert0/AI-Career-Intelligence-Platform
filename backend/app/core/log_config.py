import logging.config

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


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
        }
    )
