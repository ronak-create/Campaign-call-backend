import os
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import json
from typing import Optional, List
import sqlite3
import datetime
import asyncio
from requests.auth import HTTPBasicAuth
import requests
import uuid
from contextlib import contextmanager
import xml.etree.ElementTree as ET

app = FastAPI()

# CORS middleware for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Exotel Configuration - Support environment variables
EXOTEL_CONFIG = {
    'API_KEY': os.getenv('EXOTEL_API_KEY', 'eff1382002e915c08b49dd08486249683def80adcd97c319'),
    'API_TOKEN': os.getenv('EXOTEL_API_TOKEN', 'fe0a8652ac2b6cdb18eaff14051b3780f3d28d5a6966bc1d'),
    'SUBDOMAIN': os.getenv('EXOTEL_SUBDOMAIN', 'api.exotel.com'),
    'ACCOUNT_SID': os.getenv('EXOTEL_ACCOUNT_SID', 'wercatalyst1'),
    'APP_SID': os.getenv('EXOTEL_APP_SID', '1167841'),
    'CALLER_ID': os.getenv('EXOTEL_CALLER_ID', '08046801573')
}

# Server Configuration
BACKEND_HOST = os.getenv('BACKEND_HOST', '0.0.0.0')
BACKEND_PORT = int(os.getenv('BACKEND_PORT', '8000'))

# Database Configuration
DB_PATH = os.getenv('DATABASE_PATH', 'call_campaign.db')

# Call Configuration
CALL_INTERVAL_SECONDS = int(os.getenv('CALL_INTERVAL_SECONDS', '3'))
CALL_DETAILS_FETCH_DELAY = int(os.getenv('CALL_DETAILS_FETCH_DELAY', '5'))

@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def init_db():
    """Initialize database with required tables"""
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Campaigns table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS campaigns (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                total_calls INTEGER DEFAULT 0,
                completed_calls INTEGER DEFAULT 0,
                failed_calls INTEGER DEFAULT 0,
                active INTEGER DEFAULT 1
            )
        ''')
        
        # Calls table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS calls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                campaign_id TEXT NOT NULL,
                name TEXT NOT NULL,
                phone TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                feedback TEXT,
                timestamp TEXT,
                recording_url TEXT,
                call_sid TEXT,
                duration INTEGER,
                error_message TEXT,
                retry_count INTEGER DEFAULT 0,
                FOREIGN KEY (campaign_id) REFERENCES campaigns(id)
            )
        ''')
        
        # Campaign state table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS campaign_state (
                campaign_id TEXT PRIMARY KEY,
                is_running INTEGER DEFAULT 0,
                current_index INTEGER DEFAULT 0,
                last_updated TEXT,
                FOREIGN KEY (campaign_id) REFERENCES campaigns(id)
            )
        ''')
        
        conn.commit()
        print(f"✓ Database initialized at {DB_PATH}")

# Pydantic models
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

def get_intent_from_conversation(conversation_id):
    """
    Fetch intents by scanning conversation list
    (single conversation endpoint is unreliable in Exotel)
    """

    url = f"https://voicebot.in.exotel.com/voicebot/api/v2/accounts/{EXOTEL_CONFIG['ACCOUNT_SID']}/voicebot-conversations"

    params = {
        "fields": "insights",
        "limit": 100
    }

    response = requests.get(
        url,
        params=params,
        auth=HTTPBasicAuth(EXOTEL_CONFIG['API_KEY'], EXOTEL_CONFIG['API_TOKEN']),
        timeout=10
    )
    response.raise_for_status()

    data = response.json()

    conversations = data.get("response", [])

    for item in conversations:
        conv = item.get("data", {})
        if conv.get("conversation_id") == conversation_id:
            insights = conv.get("insights", {})
            intents_raw = insights.get("intents")

            if not intents_raw:
                return {
                    "conversation_id": conversation_id,
                    "intents": [],
                    "sentiment": insights.get("sentiment", {}).get("value"),
                    "outcome": conv.get("outcome")
                }

            intents = [i.strip() for i in intents_raw.split(",")]

            return {
                "conversation_id": conversation_id,
                "call_sid": conv.get("call_sid"),
                "intents": intents,
                "sentiment": insights.get("sentiment", {}).get("value"),
                "outcome": conv.get("outcome")
            }

    return {"error": "conversation_id not found"}

async def fetch_intents_with_retry(conversation_id: str, retries=4, delay=4):
    """
    Retry fetching intents because Exotel insights are eventually consistent.
    """
    for attempt in range(1, retries + 1):
        print(f"⏳ Fetching intents (attempt {attempt}/{retries}) for {conversation_id}")
        
        intents_info = get_intent_from_conversation(conversation_id)

        if intents_info.get("intents"):
            print("✅ Intents found:", intents_info)
            return intents_info

        await asyncio.sleep(delay)

    print("⚠ No intents found after retries")
    return intents_info


# Initialize DB on startup
@app.on_event("startup")
async def startup_event():
    print("\n" + "="*50)
    print("Call Campaign System - Starting")
    print("="*50)
    print(f"Backend: http://{BACKEND_HOST}:{BACKEND_PORT}")
    print(f"Database: {DB_PATH}")
    print(f"Exotel Account: {EXOTEL_CONFIG['ACCOUNT_SID']}")
    print("="*50 + "\n")
    
    init_db()
    
    # Resume any campaigns that were running
    asyncio.create_task(resume_campaigns())

async def resume_campaigns():
    """Resume campaigns that were running before shutdown"""
    await asyncio.sleep(2)  # Give server time to fully start
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT campaign_id FROM campaign_state 
            WHERE is_running = 1
        ''')
        running_campaigns = cursor.fetchall()
    
    if running_campaigns:
        print(f"📞 Resuming {len(running_campaigns)} campaign(s)...")
        for campaign in running_campaigns:
            campaign_id = campaign['campaign_id']
            print(f"   └─ Resuming: {campaign_id}")
            asyncio.create_task(process_campaign(campaign_id))
    else:
        print("ℹ No campaigns to resume")

@app.get("/")
def health():
    return {
        "status": "alive",
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "version": "2.0",
        "exotel_configured": bool(EXOTEL_CONFIG['API_KEY'])
    }

@app.get("/config")
def get_config():
    """Get current configuration (without sensitive data)"""
    return {
        "database": DB_PATH,
        "exotel_account": EXOTEL_CONFIG['ACCOUNT_SID'],
        "call_interval": CALL_INTERVAL_SECONDS,
        "fetch_delay": CALL_DETAILS_FETCH_DELAY
    }

@app.get("/passthru")
async def passthru(request: Request):
    """Exotel passthru endpoint - called when call is transferred to human"""
    params = dict(request.query_params)
    
    print("=== Exotel Passthru Event ===")
    for k, v in params.items():
        print(f"{k}: {v}")
    
    call_sid = params.get('CallSid')
    status = params.get('Status')
    
    if call_sid:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE calls 
                SET status = 'transferred', timestamp = ?,
                    feedback = feedback || '\nTransferred to human'
                WHERE call_sid = ?
            ''', (datetime.datetime.utcnow().isoformat(), call_sid))
            conn.commit()
            print(f"✓ Updated call {call_sid} with transfer event")
    
    return JSONResponse(
        status_code=200,
        content={
            "status": "ok",
            "received_at": datetime.datetime.utcnow().isoformat()
        }
    )

# @app.post("/webhooks/session-start")
# async def webhook_session_start(request: Request):
#     """VoiceBot webhook - triggered when voicebot session starts"""
#     try:
#         data = await request.json()
#         print(data)
#         print("=== VoiceBot Session Start ===")
#         print(f"Session ID: {data.get('session_id')}")
#         print(f"Call SID: {data.get('metadata', {}).get('call_sid')}")
        
#         call_sid = data.get('metadata', {}).get('call_sid')
        
#         if call_sid:
#             with get_db() as conn:
#                 cursor = conn.cursor()
#                 cursor.execute('''
#                     UPDATE calls 
#                     SET status = 'bot_connected',
#                         feedback = COALESCE(feedback, '') || '\nVoiceBot session started at ' || ?
#                     WHERE call_sid = ?
#                 ''', (datetime.datetime.utcnow().isoformat(), call_sid))
#                 conn.commit()
#                 print(f"✓ Updated call {call_sid} - Bot connected")
        
#         return JSONResponse(
#             status_code=200,
#             content={
#                 "http_code": 200,
#                 "response": {
#                     "data": {}
#                 }
#             }
#         )
#     except Exception as e:
#         print(f"Error in session_start webhook: {e}")
#         return JSONResponse(
#             status_code=500,
#             content={
#                 "http_code": 500,
#                 "response": {
#                     "data": None,
#                     "error_data": {
#                         "error_code": "WH001",
#                         "message": str(e),
#                         "description": "Error processing session start"
#                     }
#                 }
#             }
#         )
@app.post("/webhooks/session-start")
async def webhook_session_start(request: Request):
    try:
        data = await request.json()
        print("=== VoiceBot Session Start ===")
        # print(data)

        # call_sid = data.get("metadata", {}).get("call_sid")

        # if call_sid:
        #     with get_db() as conn:
        #         cursor = conn.cursor()
        #         cursor.execute(
        #             """
        #             UPDATE calls
        #             SET status = 'bot_connected',
        #                 feedback = COALESCE(feedback, '') || '\nVoiceBot session started at ' || ?
        #             WHERE call_sid = ?
        #             """,
        #             (datetime.datetime.utcnow().isoformat(), call_sid)
        #         )
        #         conn.commit()
        #         print(f"✓ Updated call {call_sid} - Bot connected")

        body = {
            "http_code": 200,
            "response": {
                "data": {}
            }
        }
        # body = '{"http_code":200,"response":{"data":{}}}'
        # print("RAW RESPONSE BYTES:", repr(body))


        return JSONResponse(
            status_code=200,
            content={"http_code": 200, "response": {"data": {}}}
        )

    except Exception as e:
        print("Session start error:", e)

        error_body = {
            "http_code": 500,
            "response": {
                "data": None,
                "error_data": {
                    "error_code": "WH001",
                    "message": str(e),
                    "description": "Error processing session start"
                }
            }
        }

        return Response(
            content=json.dumps(error_body),
            status_code=500,
            media_type="application/json"
        )

@app.post("/webhooks/transcript-events")
async def webhook_transcript_events(request: Request):
    """
    VoiceBot webhook - transcript events.
    First transcript arrival == bot is actively talking to user.
    Update status to 'bot_connected' ONLY ONCE.
    """
    try:
        data = await request.json()

        call_sid = data.get("metadata", {}).get("call_sid")
        events = data.get("events", [])

        if not call_sid or not events:
            return JSONResponse(status_code=200, content={"http_code": 200})

        # Check if there is at least ONE transcript event
        has_transcript = any(
            event.get("event_type") == "transcript"
            for event in events
        )

        if not has_transcript:
            return JSONResponse(status_code=200, content={"http_code": 200})

        with get_db() as conn:
            cursor = conn.cursor()

            # Read current status
            cursor.execute(
                "SELECT status FROM calls WHERE call_sid = ?",
                (call_sid,)
            )
            row = cursor.fetchone()

            if not row:
                return JSONResponse(status_code=200, content={"http_code": 200})

            current_status = row["status"]

            # Update ONLY ONCE
            if current_status not in (
                "bot_connected",
                "user_connected",
                "completed",
                "failed",
                "missed",
                "rejected",
                "bot_end",
                "user_end",
            ):
                cursor.execute(
                    """
                    UPDATE calls
                    SET status = 'bot_connected',
                        feedback = COALESCE(feedback, '') ||
                                   '\nBot started speaking at ' || ?
                    WHERE call_sid = ?
                    """,
                    (datetime.datetime.utcnow().isoformat(), call_sid)
                )
                conn.commit()
                print(f"✓ bot_connected set via transcript-events for {call_sid}")

        return JSONResponse(
            status_code=200,
            content={"http_code": 200, "response": {"data": {}}}
        )

    except Exception as e:
        print("Transcript webhook error:", e)
        return JSONResponse(
            status_code=200,
            content={"http_code": 200, "response": {"data": {}}}
        )


@app.post("/webhooks/pre-agent-transfer")
async def webhook_pre_agent_transfer(request: Request):
    """VoiceBot webhook - triggered before transferring to human agent"""
    try:
        data = await request.json()
        
        print("=== Pre-Agent Transfer ===")
        print(f"Session ID: {data.get('session_id')}")
        
        call_sid = data.get('metadata', {}).get('call_sid')
        
        if call_sid:
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE calls 
                    SET status = 'user_connected',
                        feedback = COALESCE(feedback, '') || '\nTransferring to agent at ' || ?
                    WHERE call_sid = ?
                ''', (datetime.datetime.utcnow().isoformat(), call_sid))
                conn.commit()
                print(f"✓ Updated call {call_sid} - User connected")
        
        return JSONResponse(
            status_code=200,
            content={
                "http_code": 200,
                "response": {
                    "data": {
                        "agent_transfer_message": {
                            "text": "Please hold while I connect you to our support team."
                        }
                    }
                }
            }
        )
    except Exception as e:
        print(f"Error in pre_agent_transfer webhook: {e}")
        return JSONResponse(status_code=200, content={"http_code": 200, "response": {"data": {}}})

@app.post("/webhooks/session-end")
async def webhook_session_end(request: Request):
    """VoiceBot webhook - triggered when voicebot session ends"""
    try:
        data = await request.json()
        
        print("=== VoiceBot Session End ===")
        print(f"Session ID: {data.get('session_id')}")
        
        call_sid = data.get('metadata', {}).get('call_sid')

        
        if call_sid:
            with get_db() as conn:
                cursor = conn.cursor()
                # Check current status - if user was connected, mark as user_end, otherwise bot_end
                cursor.execute('SELECT status FROM calls WHERE call_sid = ?', (call_sid,))
                current = cursor.fetchone()
                
                if current and current['status'] == 'user_connected':
                    new_status = 'user_end'
                else:
                    new_status = 'bot_end'
                
                cursor.execute('''
                    UPDATE calls 
                    SET status = ?,
                        feedback = COALESCE(feedback, '') || '\nSession ended at ' || ?
                    WHERE call_sid = ?
                ''', (new_status, datetime.datetime.utcnow().isoformat(), call_sid))
                conn.commit()
                print(f"✓ Updated call {call_sid} - Session ended ({new_status})")

        # conversation_id = data.get("conversation_id")
        # if conversation_id:
        #     asyncio.create_task(
        #         fetch_intents_with_retry(conversation_id)
        #     )
        
        return JSONResponse(
            status_code=200,
            content={
                "http_code": 200,
                "response": {
                    "data": {}
                }
            }
        )
    except Exception as e:
        print(f"Error in session_end webhook: {e}")
        return JSONResponse(status_code=200, content={"http_code": 200, "response": {"data": {}}})

@app.post("/api/campaigns/upload")
async def upload_campaign(campaign: CampaignCreate):
    """Create a new campaign from uploaded CSV data"""
    campaign_id = str(uuid.uuid4())
    created_at = datetime.datetime.utcnow().isoformat()
    
    print(f"\n📊 Creating campaign: {campaign.name}")
    print(f"   ID: {campaign_id}")
    print(f"   Calls: {len(campaign.calls)}")
    
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Create campaign
        cursor.execute('''
            INSERT INTO campaigns (id, name, created_at, total_calls, status)
            VALUES (?, ?, ?, ?, 'pending')
        ''', (campaign_id, campaign.name, created_at, len(campaign.calls)))
        
        # Insert all calls
        for call in campaign.calls:
            cursor.execute('''
                INSERT INTO calls (campaign_id, name, phone, status, feedback, timestamp, recording_url)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (campaign_id, call.name, call.phone, call.status, call.feedback, 
                  call.timestamp, call.recording_url))
        
        # Initialize campaign state
        cursor.execute('''
            INSERT INTO campaign_state (campaign_id, is_running, current_index, last_updated)
            VALUES (?, 0, 0, ?)
        ''', (campaign_id, created_at))
        
        conn.commit()
    
    print(f"✓ Campaign created successfully\n")
    
    return {
        "campaign_id": campaign_id,
        "status": "created",
        "total_calls": len(campaign.calls)
    }

@app.post("/api/campaigns/{campaign_id}/start")
async def start_campaign(campaign_id: str, background_tasks: BackgroundTasks):
    """Start or resume a campaign"""
    with get_db() as conn:
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM campaigns WHERE id = ?', (campaign_id,))
        campaign = cursor.fetchone()
        
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")
        
        cursor.execute('SELECT is_running FROM campaign_state WHERE campaign_id = ?', (campaign_id,))
        state = cursor.fetchone()
        
        if state and state['is_running']:
            return {"status": "already_running", "campaign_id": campaign_id}
        
        cursor.execute('''
            UPDATE campaign_state 
            SET is_running = 1, last_updated = ?
            WHERE campaign_id = ?
        ''', (datetime.datetime.utcnow().isoformat(), campaign_id))
        
        cursor.execute('''
            UPDATE campaigns 
            SET status = 'running'
            WHERE id = ?
        ''', (campaign_id,))
        
        conn.commit()
    
    print(f"▶ Starting campaign: {campaign_id}")
    asyncio.create_task(process_campaign(campaign_id))
    
    return {"status": "started", "campaign_id": campaign_id}

@app.post("/api/campaigns/{campaign_id}/pause")
async def pause_campaign(campaign_id: str):
    """Pause a running campaign"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE campaign_state 
            SET is_running = 0, last_updated = ?
            WHERE campaign_id = ?
        ''', (datetime.datetime.utcnow().isoformat(), campaign_id))
        
        cursor.execute('''
            UPDATE campaigns 
            SET status = 'paused'
            WHERE id = ?
        ''', (campaign_id,))
        
        conn.commit()
    
    print(f"⏸ Paused campaign: {campaign_id}")
    return {"status": "paused", "campaign_id": campaign_id}

@app.get("/api/campaigns")
async def list_campaigns():
    """List all campaigns"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT c.*, cs.is_running 
            FROM campaigns c
            LEFT JOIN campaign_state cs ON c.id = cs.campaign_id
            ORDER BY c.created_at DESC
        ''')
        campaigns = [dict(row) for row in cursor.fetchall()]
    
    return {"campaigns": campaigns}

@app.get("/api/campaigns/{campaign_id}")
async def get_campaign(campaign_id: str):
    """Get campaign details with all calls"""
    with get_db() as conn:
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM campaigns WHERE id = ?', (campaign_id,))
        campaign = cursor.fetchone()
        # print(campaign)
        
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")
        
        cursor.execute('''
            SELECT * FROM calls 
            WHERE campaign_id = ? 
            ORDER BY id ASC
        ''', (campaign_id,))
        calls = [dict(row) for row in cursor.fetchall()]
        
        cursor.execute('SELECT * FROM campaign_state WHERE campaign_id = ?', (campaign_id,))
        state = cursor.fetchone()
    
    return {
        "campaign": dict(campaign),
        "calls": calls,
        "state": dict(state) if state else None
    }

@app.get("/api/campaigns/{campaign_id}/stats")
async def get_campaign_stats(campaign_id: str):
    """Get real-time campaign statistics"""
    with get_db() as conn:
        cursor = conn.cursor()
        
        cursor.execute('''
                SELECT
                COUNT(*) AS total,

                -- final successful
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS completed,

                -- final failed outcomes
                SUM(CASE WHEN status IN ('failed','missed','rejected') THEN 1 ELSE 0 END) AS failed,

                -- still in flow
                SUM(CASE WHEN status IN ('pending','calling','bot_connected','user_connected') THEN 1 ELSE 0 END) AS pending,

                -- DONE = any terminal state
                SUM(CASE 
                    WHEN status IN ('completed','failed','missed','rejected','bot_end','user_end')
                    THEN 1 ELSE 0 
                END) AS done
                FROM calls
                WHERE campaign_id = ?
        ''', (campaign_id,))
        
        stats = dict(cursor.fetchone())
        
        cursor.execute('SELECT is_running FROM campaign_state WHERE campaign_id = ?', (campaign_id,))
        state = cursor.fetchone()
        stats['is_running'] = state['is_running'] if state else 0
    
    return stats

async def process_campaign(campaign_id: str):
    """Process all calls in a campaign"""
    print(f"\n🚀 Processing campaign: {campaign_id}")
    
    while True:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT is_running FROM campaign_state WHERE campaign_id = ?', (campaign_id,))
            state = cursor.fetchone()
            
            if not state or not state['is_running']:
                print(f"⏹ Campaign stopped: {campaign_id}\n")
                break
            
            cursor.execute('''
                SELECT * FROM calls 
                WHERE campaign_id = ? AND status = 'pending'
                ORDER BY id ASC
                LIMIT 1
            ''', (campaign_id,))
            
            call = cursor.fetchone()
        
        if not call:
            print(f"✓ Campaign completed: {campaign_id}")
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE campaign_state 
                    SET is_running = 0, last_updated = ?
                    WHERE campaign_id = ?
                ''', (datetime.datetime.utcnow().isoformat(), campaign_id))
                
                cursor.execute('''
                    UPDATE campaigns 
                    SET status = 'completed'
                    WHERE id = ?
                ''', (campaign_id,))
                
                conn.commit()
            print()
            break
        
        await make_call(campaign_id, dict(call))
        await asyncio.sleep(CALL_INTERVAL_SECONDS)

async def make_call(campaign_id: str, call_record: dict):
    """Make a single call using Exotel API"""
    call_id = call_record['id']
    phone = call_record['phone']
    name = call_record['name']
    
    print(f"📞 Calling: {name} ({phone})")
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE calls 
            SET status = 'calling', timestamp = ?
            WHERE id = ?
        ''', (datetime.datetime.utcnow().isoformat(), call_id))
        conn.commit()
    
    try:
        url = f"https://{EXOTEL_CONFIG['API_KEY']}:{EXOTEL_CONFIG['API_TOKEN']}@{EXOTEL_CONFIG['SUBDOMAIN']}/v1/Accounts/{EXOTEL_CONFIG['ACCOUNT_SID']}/Calls/connect"
        
        # data = {
        #     'From': phone,
        #     'CallerId': EXOTEL_CONFIG['CALLER_ID'],
        #     'Url': f"http://my.exotel.com/{EXOTEL_CONFIG['ACCOUNT_SID']}/exoml/start_voice/{EXOTEL_CONFIG['APP_SID']}"
        # }
        data = {
            'From': phone,
            'CallerId': EXOTEL_CONFIG['CALLER_ID'],
            'Url': f"http://my.exotel.com/{EXOTEL_CONFIG['ACCOUNT_SID']}/exoml/start_voice/{EXOTEL_CONFIG['APP_SID']}",
            'StatusCallback': 'https://campaign-call-backend.onrender.com/webhooks/status-callback',
            # 'StatusCallbackEvents[0]': 'terminal',
            'StatusCallbackContentType': 'application/json'
        }

        
        response = requests.post(url, data=data, timeout=10)
        response.raise_for_status()
        
        # Parse XML response from Exotel
        root = ET.fromstring(response.text)
        call_element = root.find('.//Call')
        
        if call_element is None:
            raise Exception("No Call element found in Exotel response")
        
        call_sid_element = call_element.find('Sid')
        if call_sid_element is None:
            raise Exception("No Sid found in Exotel response")
        
        call_sid = call_sid_element.text
        
        print(f"   ✓ Call initiated - SID: {call_sid}")
        
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE calls 
                SET call_sid = ?, status = 'calling'
                WHERE id = ?
            ''', (call_sid, call_id))
            conn.commit()
        
        # await asyncio.sleep(CALL_DETAILS_FETCH_DELAY)
        # await fetch_call_details(campaign_id, call_id, call_sid)
        
    except requests.exceptions.RequestException as e:
        error_msg = str(e)
        print(f"   ✗ Call failed: {error_msg}")
        
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE calls 
                SET status = 'failed', 
                    error_message = ?,
                    retry_count = retry_count + 1,
                    timestamp = ?
                WHERE id = ?
            ''', (error_msg, datetime.datetime.utcnow().isoformat(), call_id))
            
            cursor.execute('''
                UPDATE campaigns 
                SET failed_calls = failed_calls + 1
                WHERE id = ?
            ''', (campaign_id,))
            
            conn.commit()
    
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        print(f"   ✗ {error_msg}")
        
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE calls 
                SET status = 'failed', 
                    error_message = ?,
                    timestamp = ?
                WHERE id = ?
            ''', (error_msg, datetime.datetime.utcnow().isoformat(), call_id))
            
            cursor.execute('''
                UPDATE campaigns 
                SET failed_calls = failed_calls + 1
                WHERE id = ?
            ''', (campaign_id,))
            
            conn.commit()

@app.post("/webhooks/status-callback")
async def exotel_status_callback(request: Request):
    content_type = request.headers.get("content-type", "")

    if "application/json" in content_type:
        payload = await request.json()
    else:
        form = await request.form()
        payload = dict(form)
    # print(payload)
    call_sid = payload.get("CallSid")
    status = payload.get("Status")
    recording_url = payload.get("RecordingUrl")
    duration = payload.get("ConversationDuration", 0)

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

    with get_db() as conn:
        cursor = conn.cursor()

        # prevent double updates
        cursor.execute(
            "SELECT status, campaign_id FROM calls WHERE call_sid = ?",
            (call_sid,)
        )
        row = cursor.fetchone()

        if not row or row["status"] in ("completed", "failed", "missed", "rejected"):
            return JSONResponse(status_code=200, content={"ok": True})

        cursor.execute("""
            UPDATE calls
            SET status = ?,
                recording_url = COALESCE(?, recording_url),
                duration = ?,
                timestamp = ?
            WHERE call_sid = ?
        """, (
            final_status,
            recording_url,
            duration,
            datetime.datetime.utcnow().isoformat(),
            call_sid
        ))

        if final_status == "completed":
            cursor.execute(
                "UPDATE campaigns SET completed_calls = completed_calls + 1 WHERE id = ?",
                (row["campaign_id"],)
            )
        elif final_status == "failed":
            cursor.execute(
                "UPDATE campaigns SET failed_calls = failed_calls + 1 WHERE id = ?",
                (row["campaign_id"],)
            )

        conn.commit()

    return JSONResponse(status_code=200, content={"ok": True})


async def fetch_call_details(campaign_id: str, call_id: int, call_sid: str):
    """Fetch call details from Exotel API"""
    try:
        url = f"https://{EXOTEL_CONFIG['API_KEY']}:{EXOTEL_CONFIG['API_TOKEN']}@{EXOTEL_CONFIG['SUBDOMAIN']}/v1/Accounts/{EXOTEL_CONFIG['ACCOUNT_SID']}/Calls/{call_sid}"
        
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        # Parse XML response from Exotel
        root = ET.fromstring(response.text)
        call_element = root.find('.//Call')
        
        if call_element is None:
            raise Exception("No Call element found in Exotel response")
        
        # Extract call data from XML
        status_element = call_element.find('Status')
        duration_element = call_element.find('Duration')
        recording_element = call_element.find('RecordingUrl')
        
        status = status_element.text if status_element is not None else 'unknown'
        duration = int(duration_element.text) if duration_element is not None and duration_element.text else 0
        recording_url = recording_element.text if recording_element is not None and recording_element.text else ''
        
        status_mapping = {
            'completed': 'completed',
            'busy': 'missed',
            'no-answer': 'missed',
            'failed': 'failed',
            'canceled': 'rejected'
        }
        
        final_status = status_mapping.get(status.lower(), 'completed')
        
        print(f"   ✓ Status: {final_status} | Duration: {duration}s")
        
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE calls 
                SET status = ?,
                    duration = ?,
                    recording_url = ?,
                    timestamp = ?
                WHERE id = ?
            ''', (final_status, duration, recording_url, 
                  datetime.datetime.utcnow().isoformat(), call_id))
            
            if final_status == 'completed':
                cursor.execute('''
                    UPDATE campaigns 
                    SET completed_calls = completed_calls + 1
                    WHERE id = ?
                ''', (campaign_id,))
            elif final_status == 'failed':
                cursor.execute('''
                    UPDATE campaigns 
                    SET failed_calls = failed_calls + 1
                    WHERE id = ?
                ''', (campaign_id,))
            
            conn.commit()
        
    except Exception as e:
        print(f"   ⚠ Error fetching details: {e}")
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE calls 
                SET status = 'completed',
                    timestamp = ?
                WHERE id = ?
            ''', (datetime.datetime.utcnow().isoformat(), call_id))
            conn.commit()

@app.delete("/api/campaigns/{campaign_id}")
async def delete_campaign(campaign_id: str):
    """Delete a campaign and all its calls"""
    with get_db() as conn:
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM campaign_state WHERE campaign_id = ?', (campaign_id,))
        cursor.execute('DELETE FROM calls WHERE campaign_id = ?', (campaign_id,))
        cursor.execute('DELETE FROM campaigns WHERE id = ?', (campaign_id,))
        
        conn.commit()
    
    print(f"🗑 Deleted campaign: {campaign_id}")
    return {"status": "deleted", "campaign_id": campaign_id}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=BACKEND_HOST, port=BACKEND_PORT)
