import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parents[1]

# Runs what `celery beat` runs before scheduling (Beat.init_loader imports the app's task modules)
# in a fresh interpreter, since this test process has already imported torch.
_PROBE = """
import json, sys
from celery.apps.beat import Beat
from app.workers.beat_app import beat_app
from app.workers.celery_app import celery_app
Beat(app=beat_app).init_loader()
print(json.dumps({
    "modules": sorted(sys.modules),
    "tasks": sorted(name for name in beat_app.tasks if not name.startswith("celery.")),
    "same_schedule": beat_app.conf.beat_schedule == celery_app.conf.beat_schedule,
    "same_routes": beat_app.conf.task_routes == celery_app.conf.task_routes,
    "purge_route": beat_app.amqp.router.route({}, "accounts.purge_inactive")["queue"].name,
}))
"""


def _probe() -> dict[str, Any]:
    # PYTHONPATH pins `app` to this checkout; a shared editable venv may point elsewhere.
    env = {**os.environ, "PYTHONPATH": str(BACKEND)}
    out = subprocess.run(
        [sys.executable, "-c", _PROBE],
        cwd=BACKEND,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert out.returncode == 0, out.stderr
    result: dict[str, Any] = json.loads(out.stdout.splitlines()[-1])
    return result


def test_beat_schedules_by_name_without_importing_tasks_or_ml_libraries() -> None:
    result = _probe()

    heavy = {"torch", "sentence_transformers", "transformers", "scipy", "sklearn"}
    assert heavy.isdisjoint(result["modules"])
    assert "app.workers.tasks" not in result["modules"]
    assert result["tasks"] == []
    assert result["same_schedule"] is True
    assert result["same_routes"] is True
    assert result["purge_route"] == "celery"
