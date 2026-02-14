from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import datetime
import asyncio
from app.config import EXOTEL_CONFIG, DB_PATH, CALL_INTERVAL_SECONDS, CALL_DETAILS_FETCH_DELAY, BACKEND_HOST, BACKEND_PORT
from app.db.database import get_db
from app.db.init_db import init_db
from app.webhooks import session_wehbooks, transcript_webhook, status_callback
from app.services.campaign_service import resume_campaigns

  # multilingual (Hindi + English)

app = FastAPI()

# CORS middleware for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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


app.include_router(transcript_webhook.router)
app.include_router(session_wehbooks.router)
app.include_router(status_callback.router)




if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=BACKEND_HOST, port=BACKEND_PORT)