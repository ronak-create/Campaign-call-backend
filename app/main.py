from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
import datetime
import asyncio
from app.config import settings
from app.utils.auth import verify_token
from app.webhooks import session_wehbooks, transcript_webhook, status_callback
from app.services.campaign_service import resume_campaigns
from app.routers import campaign_router
from app.db.init_db import init_db
from app.routers import auth_router


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
    print(f"Backend: http://{settings.BACKEND_HOST}:{settings.BACKEND_PORT}")
    print(f"Database: {settings.DB_PATH}")
    print(f"Exotel Account: {settings.EXOTEL_ACCOUNT_SID}")
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
        "exotel_configured": bool(settings.EXOTEL_API_KEY)
    }

@app.get("/config", dependencies=[Depends(verify_token)])
def get_config():
    """Get current configuration (without sensitive data)"""
    return {
        "database": settings.DB_PATH,
        "exotel_account": settings.EXOTEL_ACCOUNT_SID,
        "call_interval": settings.CALL_INTERVAL_SECONDS,
        "fetch_delay": settings.CALL_DETAILS_FETCH_DELAY
    }

app.include_router(transcript_webhook.router)
app.include_router(session_wehbooks.router)
app.include_router(status_callback.router)
app.include_router(campaign_router.router)
app.include_router(auth_router.router)
