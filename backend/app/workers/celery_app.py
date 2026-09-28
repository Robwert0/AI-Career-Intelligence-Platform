from typing import Any

from celery import Celery
from celery.signals import setup_logging

from app.core.config import settings
from app.core.log_config import configure_logging


def create_celery_app(broker_url: str) -> Celery:
    app = Celery("career_intel", broker=broker_url, include=["app.workers.tasks"])
    app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        task_ignore_result=True,
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        worker_prefetch_multiplier=1,
        worker_concurrency=1,
        task_soft_time_limit=settings.job_soft_time_limit_seconds,
        task_time_limit=settings.job_soft_time_limit_seconds + 30,
        broker_connection_retry_on_startup=True,
        broker_transport_options={"socket_connect_timeout": 2, "socket_timeout": 2},
        # Bounded so a dead broker fails the HTTP request in seconds instead of hanging it.
        task_publish_retry_policy={
            "max_retries": 2,
            "interval_start": 0,
            "interval_step": 0.5,
            "interval_max": 1,
        },
    )
    return app


celery_app = create_celery_app(settings.celery_broker_url)


@setup_logging.connect
def _use_app_logging(**_: Any) -> None:
    # Connecting this signal stops Celery replacing our handlers with its own.
    configure_logging(settings.log_level)
