from app.config import settings
from app.models.schemas import CampaignCreate
import uuid
from datetime import datetime, timezone
from fastapi import HTTPException
import asyncio
from app.services.exotel_service import make_call
# from app.tasks.campaign_tasks import enqueue_campaign_calls
from app.db.unit_of_work import UnitOfWork
from app.utils.helper import clean_transcript
from app.utils.analysis_helper import send_to_analysis_service

async def resume_campaigns():
    """Resume campaigns that were running before shutdown"""
    await asyncio.sleep(2)

    async with UnitOfWork() as uow:
        running = await uow.states.get_running_campaigns()

    for campaign in running:
        asyncio.create_task(
            process_campaign(campaign["campaign_id"])
        )



async def upload_campaign(campaign: CampaignCreate):
    """Create a new campaign from uploaded CSV data"""
    campaign_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    async with UnitOfWork() as uow:

        await uow.campaigns.create_campaign(
            campaign_id,
            campaign.name,
            created_at,
            len(campaign.calls)
        )

        await uow.calls.insert_calls_bulk(
            campaign_id,
            campaign.calls
        )

        await uow.states.initialize(
            campaign_id,
            created_at
        )

    return {
        "campaign_id": campaign_id,
        "status": "created",
        "total_calls": len(campaign.calls)
    }


async def start_campaign(campaign_id: str):

    async with UnitOfWork() as uow:

        if not await uow.campaigns.exists(campaign_id):
            raise HTTPException(status_code=404, detail="Campaign not found")

        if await uow.states.is_running(campaign_id):
            return {"status": "already_running"}

        await uow.states.set_running(campaign_id, True)
        await uow.campaigns.update_status(campaign_id, "running")

    asyncio.create_task(
            process_campaign(campaign_id)
        )


    return {"status": "started"}


async def pause_campaign(campaign_id: str):

    async with UnitOfWork() as uow:
        await uow.states.pause(campaign_id)
        await uow.campaigns.mark_paused(campaign_id)

    return {"status": "paused"}


async def list_campaigns():
    async with UnitOfWork() as uow:
        campaigns = await uow.campaigns.list_with_state()
    return {"campaigns": campaigns}


async def get_campaign(campaign_id: str):

    async with UnitOfWork() as uow:
        campaign = await uow.campaigns.get_by_id(campaign_id)

        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")

        calls = await uow.calls.get_by_campaign(campaign_id)
        state = await uow.states.get_state(campaign_id)
        analysis_status = await uow.states.get_analysis_status(campaign_id)
    return {
        "campaign": campaign,
        "calls": calls,
        "state": state,
        "analysis_status": analysis_status
    }


async def get_campaign_stats(campaign_id: str):

    async with UnitOfWork() as uow:
        stats = await uow.calls.get_campaign_stats(campaign_id)
        stats["is_running"] = await uow.states.is_running(campaign_id)
        stats["analysis_status"] = await uow.states.get_analysis_status(campaign_id)
    return stats

async def get_analysis_status_and_calls_func(campaign_id: str):

    async with UnitOfWork() as uow:
        data = await uow.states.get_analysis_status_and_calls(campaign_id)

    if not data:
        raise HTTPException(status_code=404, detail="Campaign not found")

    return {
        "analysis_status": data["analysis_status"],
        "calls": data["total_calls"],
    }

async def process_campaign(campaign_id: str):

    while True:

        async with UnitOfWork() as uow:

            if not await uow.states.is_running(campaign_id):
                break

            call = await uow.calls.get_next_pending_or_retryable(campaign_id)

            if not call:
                await uow.states.set_running(campaign_id, False)
                await uow.campaigns.update_status(campaign_id, "completed")
                break

        await make_call(campaign_id, call)
        await asyncio.sleep(settings.CALL_INTERVAL_SECONDS)


async def delete_campaign(campaign_id: str):

    async with UnitOfWork() as uow:
        await uow.states.delete(campaign_id)
        await uow.calls.delete_by_campaign(campaign_id)
        await uow.campaigns.delete(campaign_id)

    return {"status": "deleted"}

async def analyze_process_campaign(campaign_id: str):
    print(f"Starting analysis for campaign {campaign_id}")
    async with UnitOfWork() as uow:
        campaign = await uow.states.get_analysis_status(campaign_id)
        if not campaign:
            raise HTTPException(status_code=404, detail="analysis status not found")

        if campaign == "processing":
            return {"status": "already_processing"}

        await uow.states.update_analysis_status(
            campaign_id,
            "processing"
        )

    asyncio.create_task(run_analysis_pipeline(campaign_id))

    return {"status": "processing_started"}

BATCH_SIZE = 5

async def run_analysis_pipeline(campaign_id: str):
    try:
        async with UnitOfWork() as uow:
            calls = await uow.states.get_calls_for_analysis(campaign_id)

        if not calls:
            async with UnitOfWork() as uow:
                await uow.states.update_analysis_status(campaign_id, "completed")
            return

        # Create batches
        batches = [
            calls[i:i + BATCH_SIZE]
            for i in range(0, len(calls), BATCH_SIZE)
        ]

        for batch in batches:
            try:
                payload = []

                for call in batch:
                    cleaned = clean_transcript(call["transcript"])
                    payload.append({
                        "call_sid": call["call_sid"],
                        "transcript": cleaned
                    })

                results = await send_to_analysis_service(payload)

                # results expected as list
                for result in results:
                    async with UnitOfWork() as uow:
                        await uow.states.update_analysis_result(
                            result.get("call_sid"),
                            result.get("city"),
                            result.get("interest"),
                            result.get("outcome")
                        )

            except Exception as e:
                print("Batch failed:", e)

        async with UnitOfWork() as uow:
            await uow.states.update_analysis_status(campaign_id, "completed")

    except Exception:
        async with UnitOfWork() as uow:
            await uow.states.update_analysis_status(campaign_id, "failed")
