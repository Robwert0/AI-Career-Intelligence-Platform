from typing import Any

from celery import Celery
from celery.signals import setup_logging
from kombu import Queue

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
        task_time_limit=settings.job_hard_time_limit_seconds,
        broker_connection_retry_on_startup=True,
        # Separate queues, so a backlog of 30-minute analyses never starves job intake when
        # two workers run (`-Q intake` and `-Q analysis`). A worker started without -Q consumes
        # every queue declared here, so a single dev worker still serves everything.
        task_queues=tuple(
            Queue(name, routing_key=name) for name in ("celery", "intake", "analysis")
        ),
        task_routes={
            "jobs.extract_job": {"queue": "intake"},
            "jobs.run_analysis": {"queue": "analysis"},
        },
        # visibility_timeout: an unacked task is redelivered after this long. It must outlast
        # the longest task, or a slow analysis would be handed to the worker a second time.
        # Settings refuses a JOB_TTL_SECONDS below the queued-plus-run worst case, and
        # test_the_broker_never_redelivers_a_running_analysis pins it against the task limit.
        broker_transport_options={
            "socket_connect_timeout": 2,
            "socket_timeout": 2,
            "visibility_timeout": settings.job_ttl_seconds,
        },
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
