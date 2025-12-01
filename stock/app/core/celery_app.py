from celery import Celery
from celery.schedules import crontab
from pythonjsonlogger import jsonlogger


import logging
import os


from .config import settings

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))

log_file = os.path.join(ROOT_DIR, 'logs', 'celery_stock.json')

logger = logging.getLogger()
logHandler = logging.FileHandler(log_file, encoding='utf-8')

log_format = (
    '%(levelname)s %(name)-12s %(asctime)s %(module)s %(process)d %(thread)d %(message)s'
)

formatter = jsonlogger.JsonFormatter(log_format)
logHandler.setFormatter(formatter)

if logger.hasHandlers():
    logger.handlers.clear()

logger.addHandler(logHandler)
logger.setLevel(logging.DEBUG)


logger = logging.getLogger(__name__)

celery_app = Celery(
    "stock",
    broker=f"{settings.CELERY_BROKER_URL}",
    backend=f"{settings.CELERY_RESULT_BACKEND}",
)

celery_app.conf.update(
    timezone="Europe/Warsaw",
    enable_utc=False,
    task_serializer="json",
    task_track_started=True,
    result_serializer="json",
    accept_content=["application/json"],
    result_backend_max_retries=10,
    task_send_sent_event=True,
    result_extended=True,
    result_backend_always_retry=True,
    result_expires=3600,
    task_time_limit=5 * 60,
    task_soft_time_limit=5 * 60,
    worker_send_task_events=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_default_retry_delay=300,
    task_max_retries=3,
    task_default_queue="stock_tasks",
    task_create_missing_queues=True,
    worker_max_tasks_per_child=1000,
    worker_max_memory_per_child=50000,
    worker_log_format="[%(asctime)s: %(levelname)s/%(processName)s] %(message)s",
    worker_task_log_format="[%(asctime)s: %(levelname)s/%(processName)s][%(task_name)s(%(task_id)s)] %(message)s",
)

celery_app.autodiscover_tasks(
    packages=["app.core.tasks"],
    related_name="tasks",
    force=True,
)


celery_app.conf.beat_schedule = {
    "ingest-gpw-quarter-main": {
        "task": "ingest_gpw_quarter",
        "schedule": crontab(minute="30", hour="9-17", day_of_week="0-6"),
        "options": {"queue": "stock_tasks"},
    },

    "ingest-gpw-quarter-alt": {
        "task": "ingest_gpw_quarter_alt",
        "schedule": crontab(minute="0,15,45", hour="9-17", day_of_week="1-5"),
        "options": {"queue": "stock_tasks"},
    },
}
