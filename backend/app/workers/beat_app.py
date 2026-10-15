from app.core.config import settings
from app.workers.celery_app import create_celery_app

# Beat sends scheduled tasks by name and only needs the schedule and routes. The worker app's
# `include` would import tasks.py and with it torch: ~400 MiB of RSS to fire one task a day.
beat_app = create_celery_app(settings.celery_broker_url, include=())
