from app.db.unit_of_work import UnitOfWork
from app.celery_app import celery_app
from app.tasks.call_tasks import make_call_task
from app.config import settings


@celery_app.task
def enqueue_campaign_calls(campaign_id):

    with UnitOfWork() as uow:
        calls = uow.calls.get_all_pending(campaign_id)

    for index, call in enumerate(calls):

        make_call_task.apply_async(
            args=[campaign_id, call["id"]],
            countdown=index * settings.CALL_INTERVAL_SECONDS
        )
