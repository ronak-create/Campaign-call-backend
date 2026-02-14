from app.celery_app import celery_app
from app.db.unit_of_work import UnitOfWork
from app.services.exotel_service import make_call
import asyncio


@celery_app.task(bind=True, max_retries=3, default_retry_delay=10)
def make_call_task(self, campaign_id: str, call_id: int):

    try:
        # 1️⃣ Fetch call safely
        with UnitOfWork() as uow:
            call = uow.calls.get_by_id(call_id)

            if not call:
                print(f"Call {call_id} not found.")
                return

            # Prevent retrying completed calls
            if call["status"] not in ("pending", "calling"):
                print(f"Call {call_id} already processed.")
                return

        # 2️⃣ Execute async call logic
        asyncio.run(make_call(campaign_id, call))

        # 3️⃣ After call execution, check campaign completion
        with UnitOfWork() as uow:
            remaining = uow.calls.count_pending(campaign_id)

            if remaining == 0:
                uow.campaigns.update_status(campaign_id, "completed")
                uow.states.set_running(campaign_id, False)

    except Exception as exc:
        print(f"Error in make_call_task: {exc}")
        raise self.retry(exc=exc)
