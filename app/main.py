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
from app.db.unit_of_work import UnitOfWork
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from app.routers.campaign_router import limiter


async def orphan_cleanup_loop():
    while True:
        await asyncio.sleep(600)
        try:
            async with UnitOfWork() as uow:
                await uow.calls.mark_stale_calling_as_failed(10)
        except Exception as e:
            print(f"Cleanup error: {e}")


  # multilingual (Hindi + English)

if settings.SENTRY_DSN:
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        integrations=[FastApiIntegration()],
        traces_sample_rate=0.2,
    )

app = FastAPI()

# CORS middleware for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

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

    asyncio.create_task(orphan_cleanup_loop())

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

@app.get("/health")
async def health_check():
    return {"status": "ok"}

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
