import os

from celery import Celery
from django.conf import settings

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("session")

app.config_from_object("django.conf:settings", namespace="CELERY")

app.conf.update(
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
    task_default_queue="financial_tasks",
    task_create_missing_queues=True,
    worker_max_tasks_per_child=1000,
    worker_max_memory_per_child=50000,
    worker_log_format="[%(asctime)s: %(levelname)s/%(processName)s] %(message)s",
    worker_task_log_format="[%(asctime)s: %(levelname)s/%(processName)s][%(task_name)s(%(task_id)s)] %(message)s",
)

app.autodiscover_tasks(lambda: settings.INSTALLED_APPS)
