from pydantic import BaseModel
from typing import Optional, List

class CallRecord(BaseModel):
    name: str
    phone: str
    status: Optional[str] = 'pending'
    feedback: Optional[str] = None
    timestamp: Optional[str] = None
    recording_url: Optional[str] = None

class CampaignCreate(BaseModel):
    name: str
    calls: List[CallRecord]

class CampaignResponse(BaseModel):
    id: str
    name: str
    status: str
    total_calls: int
    completed_calls: int
    failed_calls: int
    created_at: str
