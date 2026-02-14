from app.db.database import get_db
from app.config import settings
import requests
from datetime import datetime, timezone 
from xml.etree import ElementTree as ET
from app.config import settings
from app.db.unit_of_work import UnitOfWork

async def make_call(campaign_id: str, call_record: dict):

    call_id = call_record['id']
    phone = call_record['phone']
    name = call_record['name']

    print(f"📞 Calling: {name} ({phone})")

    # Mark calling (separate small transaction)
    with UnitOfWork() as uow:
        uow.calls.mark_calling(
            call_id,
            datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        )

    try:
        url = f"https://{settings.EXOTEL_API_KEY}:{settings.EXOTEL_API_TOKEN}@{settings.EXOTEL_SUBDOMAIN}/v1/Accounts/{settings.EXOTEL_ACCOUNT_SID}/Calls/connect"

        data = {
            'From': phone,
            'CallerId': settings.EXOTEL_CALLER_ID,
            'Url': f"http://my.exotel.com/{settings.EXOTEL_ACCOUNT_SID}/exoml/start_voice/{settings.EXOTEL_APP_SID}",
            'StatusCallback': 'https://e105-2402-a00-142-98d-a4f0-211e-db5d-9e64.ngrok-free.app/webhooks/status-callback',
            'StatusCallbackContentType': 'application/json'
        }

        response = requests.post(url, data=data, timeout=10)
        response.raise_for_status()
        print("✅ Call request accepted:", response.text)
        root = ET.fromstring(response.text)
        call_element = root.find('.//Call')
        if call_element is None:
            raise Exception("No Call element found")

        call_sid = call_element.find('Sid').text

        print(f"✓ Call initiated - SID: {call_sid}")

        # Save call_sid (small transaction)
        with UnitOfWork() as uow:
            uow.calls.save_call_sid(call_id, call_sid)

    except Exception as e:

        error_msg = str(e)
        print(f"✗ Call failed: {error_msg}")

        # Atomic failure update
        with UnitOfWork() as uow:
            uow.calls.mark_failed(
                call_id,
                error_msg,
                datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
            )
            uow.campaigns.increment_failed(campaign_id)

async def fetch_call_details(campaign_id: str, call_id: int, call_sid: str):

    try:
        url = f"https://{settings.EXOTEL_API_KEY}:{settings.EXOTEL_API_TOKEN}@{settings.EXOTEL_SUBDOMAIN}/v1/Accounts/{settings.EXOTEL_ACCOUNT_SID}/Calls/{call_sid}"

        response = requests.get(url, timeout=10)
        response.raise_for_status()

        root = ET.fromstring(response.text)
        call_element = root.find('.//Call')
        if call_element is None:
            raise Exception("No Call element found")

        status = call_element.find('Status').text
        duration = int(call_element.find('Duration').text or 0)
        recording_url = call_element.find('RecordingUrl').text or ""

        status_mapping = {
            'completed': 'completed',
            'busy': 'missed',
            'no-answer': 'missed',
            'failed': 'failed',
            'canceled': 'rejected'
        }

        final_status = status_mapping.get(status.lower(), 'completed')

        print(f"✓ Status: {final_status} | Duration: {duration}s")

        with UnitOfWork() as uow:

            uow.calls.update_after_fetch(
                call_id,
                final_status,
                duration,
                recording_url,
                datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

            )

            if final_status == "completed":
                uow.campaigns.increment_completed(campaign_id)

            elif final_status == "failed":
                uow.campaigns.increment_failed(campaign_id)

    except Exception as e:
        print(f"⚠ Error fetching details: {e}")

        # fallback minimal safe update
        with UnitOfWork() as uow:
            uow.calls.mark_failed(
                call_id,
                str(e),
                datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
            )