from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "storyverse_agent",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.update(
    task_default_queue="default",
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)

# Ensure tasks are imported and registered.
celery_app.autodiscover_tasks(["app.tasks"])
