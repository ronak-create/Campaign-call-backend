from celery import Celery
from app.config import settings

# Create Celery instance
celery_app = Celery(
    "call_campaign",
    broker=settings.REDIS_BROKER_URL,
    backend=settings.REDIS_BACKEND_URL
)

# Optional but recommended configuration
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)

# Auto-discover tasks inside app.tasks
import app.tasks.call_tasks
import app.tasks.campaign_tasks