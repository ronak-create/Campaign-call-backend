from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from app.db.unit_of_work import UnitOfWork
import datetime

router = APIRouter()

@router.post("/webhooks/status-callback")
async def exotel_status_callback(request: Request):

    content_type = request.headers.get("content-type", "")

    if "application/json" in content_type:
        payload = await request.json()
    else:
        form = await request.form()
        payload = dict(form)

    call_sid = payload.get("CallSid")
    status = payload.get("Status")
    recording_url = payload.get("RecordingUrl")

    status_mapping = {
        "completed": "completed",
        "busy": "missed",
        "no-answer": "missed",
        "failed": "failed",
        "canceled": "rejected"
    }

    final_status = status_mapping.get(str(status).lower())

    if not call_sid or not final_status:
        return JSONResponse(status_code=200, content={"ok": True})

    with UnitOfWork() as uow:

        row = uow.calls.get_call_status_and_campaign(call_sid)

        if not row or row["status"] in ("completed", "failed", "missed", "rejected"):
            return JSONResponse(status_code=200, content={"ok": True})

        timestamp = datetime.datetime.utcnow().isoformat()

        uow.calls.update_status_from_callback(
            call_sid,
            final_status,
            recording_url,
            timestamp
        )

        if final_status == "completed":
            uow.campaigns.increment_completed(row["campaign_id"])

        elif final_status == "failed":
            uow.campaigns.increment_failed(row["campaign_id"])

    return JSONResponse(status_code=200, content={"ok": True})
