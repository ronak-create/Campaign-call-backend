from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
import datetime
# from app.utils.helper import extract_preferred_city_from_events
from app.db.unit_of_work import UnitOfWork

router = APIRouter()

@router.post("/webhooks/transcript-events")
async def webhook_transcript_events(request: Request):

    try:
        data = await request.json()

        call_sid = data.get("external_id")
        events = data.get("events", [])

        if not call_sid or not events:
            return JSONResponse(status_code=200, content={"http_code": 200})

        has_transcript = any(
            e.get("event_type") == "transcript"
            for e in events
        )

        if not has_transcript:
            return JSONResponse(status_code=200, content={"http_code": 200})

        # preferred_city = extract_preferred_city_from_events(events)

        with UnitOfWork() as uow:

            # if preferred_city:
            #     uow.calls.update_preferred_city(call_sid, preferred_city)

            uow.calls.mark_bot_connected_if_needed(
                call_sid
            )

        return JSONResponse(
            status_code=200,
            content={"http_code": 200, "response": {"data": {}}}
        )

    except Exception:
        return JSONResponse(
            status_code=200,
            content={"http_code": 200, "response": {"data": {}}}
        )
