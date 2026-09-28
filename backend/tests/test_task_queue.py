import threading
import time
from typing import Any

import pytest

from app.workers.celery_app import create_celery_app
from app.workers.queue import CeleryTaskQueue, QueueUnavailableError


async def test_enqueue_sends_only_the_job_id_off_the_event_loop() -> None:
    calls: list[tuple[str, dict[str, Any], int]] = []

    def send(name: str, **kwargs: Any) -> None:
        calls.append((name, kwargs, threading.get_ident()))

    await CeleryTaskQueue(send=send).enqueue("jobs.ping", "A" * 22)

    [(name, kwargs, thread)] = calls
    assert name == "jobs.ping"
    assert kwargs == {"args": ["A" * 22]}
    # send_task does blocking socket I/O; on the loop thread it would stall every request.
    assert thread != threading.get_ident()


async def test_an_unreachable_broker_fails_fast() -> None:
    dead = create_celery_app("redis://127.0.0.1:1/0")
    started = time.monotonic()

    with pytest.raises(QueueUnavailableError):
        await CeleryTaskQueue(send=dead.send_task).enqueue("jobs.ping", "A" * 22)

    assert time.monotonic() - started < 10
