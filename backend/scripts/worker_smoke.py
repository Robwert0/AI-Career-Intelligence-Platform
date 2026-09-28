import argparse
import asyncio
import sys
import time

from app.core.config import settings
from app.core.job_store import JobStatus, JobStore
from app.core.redis import create_redis
from app.workers.queue import CeleryTaskQueue


async def smoke(timeout: float) -> bool:
    redis = create_redis()
    try:
        store = JobStore(redis, ttl_seconds=settings.job_ttl_seconds)
        record = await store.create("ping", "worker-smoke", now=time.time())
        await CeleryTaskQueue().enqueue("jobs.ping", record.id)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            current = await store.load(record.id)
            if current is not None and current.status is JobStatus.DONE:
                return True
            await asyncio.sleep(0.5)
        return False
    finally:
        await redis.aclose()


def main() -> int:
    parser = argparse.ArgumentParser(description="Check a live Celery worker completes a job.")
    parser.add_argument("--timeout", type=float, default=30.0, help="seconds to wait")
    args = parser.parse_args()
    if asyncio.run(smoke(args.timeout)):
        print("worker ok")
        return 0
    print("worker did not complete the ping job in time", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
