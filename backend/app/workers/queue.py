import asyncio
from collections.abc import Callable
from typing import Protocol

from kombu.exceptions import OperationalError

from app.workers.celery_app import celery_app


class QueueUnavailableError(Exception):
    """The broker could not accept the task; the job will never run unless re-enqueued."""


class TaskQueue(Protocol):
    async def enqueue(self, task_name: str, job_id: str) -> None: ...


class CeleryTaskQueue:
    def __init__(self, send: Callable[..., object] = celery_app.send_task) -> None:
        self._send = send

    async def enqueue(self, task_name: str, job_id: str) -> None:
        try:
            await asyncio.to_thread(self._send, task_name, args=[job_id])
        except OperationalError as exc:
            raise QueueUnavailableError(task_name) from exc
