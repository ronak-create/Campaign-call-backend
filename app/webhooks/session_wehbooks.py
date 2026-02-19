from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from datetime import datetime as dt
import json
from app.db.unit_of_work import UnitOfWork
from app.utils.helper import extract_city_from_session
from app.utils.helper import extract_transcript_from_session

router = APIRouter()


@router.post("/webhooks/session-start")
async def webhook_session_start(request: Request):
    try:
        data = await request.json()
        print("Session Start Payload: ", data)
        call_sid = data.get("external_id")
        current_conversation_id = data.get("conversation_id")
        previous_sessions = data.get("previous_sessions", {}).get("sessions", [])

        with UnitOfWork() as uow:

            if call_sid:
                uow.calls.mark_bot_connected(
                    call_sid,
                    current_conversation_id
                )
            for session in previous_sessions:
                conversation_id = session.get("conversation_id")
                if not conversation_id:
                    continue
                if not uow.calls.exists_by_conversation(conversation_id):
                    continue
                print(f"session: {session}")
                justification = session.get("call_outcome", {}).get("justification", "")
                print(f"justification: {justification}")
                intents = session.get("intents", [])

                city = extract_city_from_session(session)
                print(f"extracted city: {city}")

                interested = "no"
                for intent_obj in intents:
                    if intent_obj.get("intent", "").replace(" ", "") == "RIDER_RESEARCH":
                        interested = "yes"
                        break
                uow.calls.update_justification_and_interest(
                    conversation_id,
                    city,
                    justification,
                    interested
                )
                print("justification added")

        return JSONResponse(
            status_code=200,
            content=
            {
                "response": {
                    "http_code": 200,
                    "method": "POST",
                    "request_id": "any-string",
                    "response": {
                        "http_code": 200,
                        "data": {}
                    }
                }
            }
        )

    except Exception as e:
        return Response(
            content=json.dumps({
                "http_code": 500,
                "error": str(e)
            }),
            status_code=500,
            media_type="application/json"
        )

@router.post("/webhooks/session-end")
async def webhook_session_end(request: Request):
    try:
        data = await request.json()
        call_sid = data.get('metadata', {}).get('call_sid')
        start_time_str = data.get('start_time')
        end_time_str = data.get('end_time')

        if not call_sid:
            return JSONResponse(status_code=200, content={"http_code": 200})

        duration_seconds = 0

        if start_time_str and end_time_str:
            start_time = dt.fromisoformat(start_time_str.replace("Z", "+00:00"))
            end_time = dt.fromisoformat(end_time_str.replace("Z", "+00:00"))
            duration_seconds = int((end_time - start_time).total_seconds())

        transcript_text = extract_transcript_from_session(data)

        with UnitOfWork() as uow:

            current = uow.calls.get_status_by_sid(call_sid)

            if current and current["status"] == "user_connected":
                new_status = "user_end"
            else:
                new_status = "bot_end"

            uow.calls.mark_session_end(
                call_sid,
                new_status,
                duration_seconds
            )

            # Only update transcript if we actually extracted something
            if transcript_text:
                uow.calls.update_transcript(
                    call_sid,
                    transcript_text
                )

        return JSONResponse(
            status_code=200,
            content={"http_code": 200, "response": {"data": {}}}
        )

    except Exception as e:
        print("Session end error:", str(e))
        return JSONResponse(
            status_code=200,
            content={"http_code": 200, "response": {"data": {}}}
        )
