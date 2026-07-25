"""
Celery app for background AASIST inference.

Run with:
    celery -A backend.workers.celery_app worker --loglevel=info
(from the project root — same reason `uvicorn backend.main:app` needs to run
from there: everything imports via the `backend.` package prefix.)
"""
from celery import Celery

from backend.config import get_settings

settings = get_settings()

celery_app = Celery(
    "aurivo",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Nothing in this app calls .get()/.result on a task — the frontend
    # polls the Investigation row's status directly via the API, not
    # Celery's result backend. Ignoring results means dispatching a task
    # never needs the result backend at all, which both avoids pointless
    # Redis round-trips on every upload and makes a broker outage fail
    # fast instead of also retrying an unused result-tracking connection.
    task_ignore_result=True,
    # AASIST inference is CPU/GPU-bound and can take a few seconds per file;
    # avoid a worker holding a task forever if the model wrapper hangs.
    task_time_limit=300,
    task_soft_time_limit=240,
)

celery_app.autodiscover_tasks(["backend.workers"])
