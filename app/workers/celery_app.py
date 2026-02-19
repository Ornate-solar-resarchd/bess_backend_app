from __future__ import annotations

from celery import Celery

from app.core.config import settings


celery_app = Celery(
    "bess_workers",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.domains.engineer.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)
