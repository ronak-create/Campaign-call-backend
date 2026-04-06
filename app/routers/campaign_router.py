from fastapi import APIRouter, Depends, Request
from app.models.schemas import CampaignCreate
from app.services import campaign_service
from app.utils.auth import verify_token
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

router = APIRouter(prefix="/api/campaigns", tags=["Campaigns"],dependencies=[Depends(verify_token)])


@router.post("/upload")
@limiter.limit("10/minute")
async def upload_campaign(request: Request, campaign: CampaignCreate):
    return await campaign_service.upload_campaign(campaign)


@router.post("/{campaign_id}/start")
async def start_campaign(campaign_id: str):
    return await campaign_service.start_campaign(campaign_id)

@router.post("/{campaign_id}/process")
async def process_campaign(campaign_id: str):
    return await campaign_service.process_campaign(campaign_id)

@router.post("/{campaign_id}/pause")
async def pause_campaign(campaign_id: str):
    return await campaign_service.pause_campaign(campaign_id)


@router.post("/{campaign_id}/analyze")
async def analyze_campaign(campaign_id: str):
    return await campaign_service.analyze_process_campaign(campaign_id)

# @router.get("/{campaign_id}/analysis_status")
# async def get_analysis_status_func(campaign_id: str):
#     return await campaign_service.get_analysis_status_and_calls_func(campaign_id)

@router.get("")
async def list_campaigns():
    return await campaign_service.list_campaigns()


@router.get("/{campaign_id}")
async def get_campaign(campaign_id: str):
    return await campaign_service.get_campaign(campaign_id)


@router.get("/{campaign_id}/stats")
async def get_stats(campaign_id: str):
    return await campaign_service.get_campaign_stats(campaign_id)


@router.delete("/{campaign_id}")
async def delete_campaign(campaign_id: str):
    return await campaign_service.delete_campaign(campaign_id)
