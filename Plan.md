# PLAN.md — Production Migration Agent Instructions

> **Agent:** Read this file completely before touching any code.  
> **Execution order:** Phase 1 → 2 → 3 → 4 → 5. Complete every task in a phase before moving to the next.  
> **After every file change:** verify all imports in that file are consistent before moving on.  
> **Python target:** 3.11  
> **SQL placeholder style:** `asyncpg` uses `$1, $2, $3...` — replace ALL `?` placeholders in raw SQL strings accordingly.

---

## Ground rules

- Do NOT add any new API endpoints except `/health` (added in Phase 5).
- Do NOT modify any webhook logic except changing `with UnitOfWork()` → `async with UnitOfWork()` and adding `await` to repo calls.
- Do NOT change any business logic — campaign flow, analysis flow, Exotel integration behaviour stays identical.
- Do NOT touch `index.html` — that is handled externally.
- Keep `await asyncio.sleep(settings.CALL_INTERVAL_SECONDS)` in `process_campaign` as-is.
- After completing all phases, run a final import check across every modified file.

---

## Phase 1 — Bug fixes (no dependency changes)

### Task 1.1 — Fix broken SQL tuple in `call_repo.py`

File: `app/repositories/call_repo.py`  
Method: `mark_bot_connected_if_needed`

Find this line:
```python
self.cursor.execute("""
    UPDATE calls
    SET status = 'bot_connected'
    WHERE call_sid = ?
    AND status NOT IN (...)
""", (call_sid))
```

Change `(call_sid)` → `(call_sid,)` — the trailing comma is mandatory to make it a tuple.

---

### Task 1.2 — Remove duplicate method in `call_repo.py`

File: `app/repositories/call_repo.py`

There are two definitions of `get_status_by_sid`. Delete the **first** one (it appears around line 95, before `mark_session_end`). Keep only the second definition.

---

### Task 1.3 — Remove hardcoded URL in `exotel_service.py`

File: `app/services/exotel_service.py`

Find:
```python
'StatusCallback': 'https://campaign-call-backend.onrender.com/webhooks/status-callback',
```

Replace with:
```python
'StatusCallback': f"{settings.CALLBACK_BASE_URL}/webhooks/status-callback",
```

---

### Task 1.4 — Add new config fields to `config.py`

File: `app/config.py`

Inside `__init__`, add these three lines after the existing fields:
```python
self.CALLBACK_BASE_URL = os.getenv('CALLBACK_BASE_URL', 'http://localhost:8000')
self.DATABASE_URL = os.getenv('DATABASE_URL')
self.SENTRY_DSN = os.getenv('SENTRY_DSN', '')
```

In `_validate`, do NOT add `DATABASE_URL` to the required list — it can be absent in local dev with SQLite fallback handled externally.

---

### Task 1.5 — Delete dead file

Delete `backend.py` from the project root. It has broken imports and is not used anywhere.

---

## Phase 2 — Async HTTP client

### Task 2.1 — Update `requirements.txt`

Add these lines to `requirements.txt` (append at end, do not remove anything existing):
```
httpx
sentry-sdk[fastapi]
slowapi
sqlalchemy[asyncio]
asyncpg
alembic
```

---

### Task 2.2 — Replace `requests` with `httpx` in `exotel_service.py`

File: `app/services/exotel_service.py`

Remove: `import requests`  
Add: `import httpx`

In `make_call`, replace:
```python
response = requests.post(url, data=data, timeout=10)
response.raise_for_status()
```
With:
```python
async with httpx.AsyncClient(timeout=10) as client:
    response = await client.post(url, data=data)
    response.raise_for_status()
```

In `fetch_call_details`, replace:
```python
response = requests.get(url, timeout=10)
response.raise_for_status()
```
With:
```python
async with httpx.AsyncClient(timeout=10) as client:
    response = await client.get(url)
    response.raise_for_status()
```

Both functions are already `async def` — this is a drop-in swap.

---

## Phase 3 — Postgres + async SQLAlchemy

> **Note:** The DATABASE_URL format for asyncpg is:  
> `postgresql+asyncpg://user:password@host:port/dbname`  
> This will be provided as an environment variable externally. The code must support it.

---

### Task 3.1 — Replace `app/db/database.py` entirely

Overwrite the file with:
```python
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from contextlib import asynccontextmanager
from app.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

@asynccontextmanager
async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
```

---

### Task 3.2 — Replace `app/db/unit_of_work.py` entirely

Overwrite the file with:
```python
from app.db.database import get_db
from app.repositories.campaign_repo import CampaignRepository
from app.repositories.call_repo import CallRepository
from app.repositories.campaign_state_repo import CampaignStateRepository


class UnitOfWork:

    async def __aenter__(self):
        self._ctx = get_db()
        self.conn = await self._ctx.__aenter__()
        self.campaigns = CampaignRepository(self.conn)
        self.calls = CallRepository(self.conn)
        self.states = CampaignStateRepository(self.conn)
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if exc_type:
            await self.conn.rollback()
        else:
            await self.conn.commit()
        await self._ctx.__aexit__(exc_type, exc, tb)
```

---

### Task 3.3 — Convert all repository classes to async

Apply the following changes to ALL THREE repo files:  
`app/repositories/call_repo.py`  
`app/repositories/campaign_repo.py`  
`app/repositories/campaign_state_repo.py`

Rules for every method in every repo:

1. Change `def method_name` → `async def method_name`
2. Change `self.cursor = conn.cursor()` → remove this line entirely from `__init__`. The `conn` is now an `AsyncSession` and executes directly.
3. Change `self.cursor.execute(sql, params)` → `await self.conn.execute(text(sql), params_as_dict)`
4. Change `self.cursor.fetchone()` → `result = await self.conn.execute(...); row = result.fetchone()`
5. Change `self.cursor.fetchall()` → `result = await self.conn.execute(...); rows = result.fetchall()`
6. Change all `?` placeholders to named params: `$1, $2...` style does NOT work with SQLAlchemy `text()` — use `:param_name` style instead. Example: `WHERE id = :id` with `{"id": value}`.
7. Add `from sqlalchemy import text` at the top of each repo file.
8. Remove `self.cursor` from `__init__` entirely.

Example transformation:
```python
# BEFORE
def mark_calling(self, call_id: int, timestamp: str):
    self.cursor.execute("""
        UPDATE calls SET status = 'calling', timestamp = ? WHERE id = ?
    """, (timestamp, call_id))

# AFTER
async def mark_calling(self, call_id: int, timestamp: str):
    await self.conn.execute(text("""
        UPDATE calls SET status = 'calling', timestamp = :timestamp WHERE id = :id
    """), {"timestamp": timestamp, "id": call_id})
```

For `fetchone` with dict conversion:
```python
# BEFORE
row = self.cursor.fetchone()
return dict(row) if row else None

# AFTER
result = await self.conn.execute(text(sql), params)
row = result.fetchone()
return dict(row._mapping) if row else None
```

For `fetchall` with dict conversion:
```python
result = await self.conn.execute(text(sql), params)
return [dict(row._mapping) for row in result.fetchall()]
```

---

### Task 3.4 — Update all services and webhooks to use `async with UnitOfWork()`

Files to update:
- `app/services/campaign_service.py`
- `app/services/exotel_service.py`
- `app/webhooks/session_wehbooks.py`
- `app/webhooks/status_callback.py`
- `app/webhooks/transcript_webhook.py`

Change every occurrence of:
```python
with UnitOfWork() as uow:
```
To:
```python
async with UnitOfWork() as uow:
```

And every `uow.calls.some_method(...)` → `await uow.calls.some_method(...)`  
And every `uow.campaigns.some_method(...)` → `await uow.campaigns.some_method(...)`  
And every `uow.states.some_method(...)` → `await uow.states.some_method(...)`

All functions that contain `async with UnitOfWork()` must themselves be `async def` — verify this for every webhook handler.

---

### Task 3.5 — Replace `app/db/init_db.py` with Alembic-based setup

Alembic will handle schema. Overwrite `app/db/init_db.py` with:
```python
def init_db():
    """Schema is managed by Alembic migrations. This is a no-op kept for import compatibility."""
    print("Schema managed by Alembic. Run: alembic upgrade head")
```

Then initialise Alembic from the project root. Create `alembic.ini` and `alembic/` directory with `alembic init alembic`.

Edit `alembic/env.py` — set the `sqlalchemy.url` to read from environment:
```python
import os
config.set_main_option("sqlalchemy.url", os.getenv("DATABASE_URL", ""))
```

Create the first migration file manually in `alembic/versions/001_initial_schema.py` that recreates the three tables from the original `init_db.py`:

```python
"""initial schema

Revision ID: 001
Create Date: 2025-01-01
"""
from alembic import op
import sqlalchemy as sa

def upgrade():
    op.create_table('campaigns',
        sa.Column('id', sa.Text, primary_key=True),
        sa.Column('name', sa.Text, nullable=False),
        sa.Column('created_at', sa.Text, nullable=False),
        sa.Column('status', sa.Text, server_default='pending'),
        sa.Column('total_calls', sa.Integer, server_default='0'),
        sa.Column('completed_calls', sa.Integer, server_default='0'),
        sa.Column('failed_calls', sa.Integer, server_default='0'),
        sa.Column('active', sa.Integer, server_default='1'),
    )
    op.create_table('calls',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('campaign_id', sa.Text, sa.ForeignKey('campaigns.id'), nullable=False),
        sa.Column('name', sa.Text, nullable=False),
        sa.Column('phone', sa.Text, nullable=False),
        sa.Column('status', sa.Text, server_default='pending'),
        sa.Column('feedback', sa.Text),
        sa.Column('timestamp', sa.Text),
        sa.Column('recording_url', sa.Text),
        sa.Column('call_sid', sa.Text),
        sa.Column('conversation_id', sa.Text),
        sa.Column('duration', sa.Integer),
        sa.Column('error_message', sa.Text),
        sa.Column('retry_count', sa.Integer, server_default='0'),
        sa.Column('preferred_city', sa.Text),
        sa.Column('interested', sa.Text),
        sa.Column('transcript', sa.Text),
        sa.Column('analysis_status', sa.Text, server_default='pending'),
    )
    op.create_table('campaign_state',
        sa.Column('campaign_id', sa.Text, sa.ForeignKey('campaigns.id'), primary_key=True),
        sa.Column('is_running', sa.Integer, server_default='0'),
        sa.Column('current_index', sa.Integer, server_default='0'),
        sa.Column('analysis_status', sa.Text, server_default='not_started'),
        sa.Column('last_updated', sa.Text),
    )

def downgrade():
    op.drop_table('campaign_state')
    op.drop_table('calls')
    op.drop_table('campaigns')
```

---

## Phase 4 — Retry logic + orphan cleanup

### Task 4.1 — Add two new methods to `call_repo.py`

Add these two async methods to `CallRepository`:

```python
async def get_next_pending_or_retryable(self, campaign_id: str):
    result = await self.conn.execute(text("""
        SELECT * FROM calls
        WHERE campaign_id = :campaign_id
        AND (status = 'pending' OR (status = 'failed' AND retry_count < 3))
        ORDER BY id ASC
        LIMIT 1
    """), {"campaign_id": campaign_id})
    row = result.fetchone()
    return dict(row._mapping) if row else None

async def mark_stale_calling_as_failed(self, cutoff_minutes: int = 10):
    await self.conn.execute(text("""
        UPDATE calls
        SET status = 'failed',
            error_message = 'call timed out - marked by cleanup'
        WHERE status = 'calling'
        AND timestamp < NOW() - INTERVAL ':minutes minutes'
    """), {"minutes": cutoff_minutes})
```

---

### Task 4.2 — Use retryable query in `campaign_service.py`

File: `app/services/campaign_service.py`

In `process_campaign`, change:
```python
call = await uow.calls.get_next_pending_call(campaign_id)
```
To:
```python
call = await uow.calls.get_next_pending_or_retryable(campaign_id)
```

---

### Task 4.3 — Add orphan cleanup loop to `app/main.py`

Add this function before `startup_event`:
```python
async def orphan_cleanup_loop():
    while True:
        await asyncio.sleep(600)
        try:
            async with UnitOfWork() as uow:
                await uow.calls.mark_stale_calling_as_failed(10)
        except Exception as e:
            print(f"Cleanup error: {e}")
```

Inside `startup_event`, add:
```python
asyncio.create_task(orphan_cleanup_loop())
```

Make sure `UnitOfWork` is imported at the top of `main.py`.

---

## Phase 5 — Observability + rate limiting + health endpoint

### Task 5.1 — Add Sentry to `app/main.py`

At the top of `app/main.py`, after existing imports, add:
```python
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
```

Before `app = FastAPI()`, add:
```python
if settings.SENTRY_DSN:
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        integrations=[FastApiIntegration()],
        traces_sample_rate=0.2,
    )
```

---

### Task 5.2 — Add rate limiter to upload endpoint

File: `app/routers/campaign_router.py`

Add imports at top:
```python
from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
```

Change the upload route:
```python
@router.post("/upload")
@limiter.limit("10/minute")
async def upload_campaign(request: Request, campaign: CampaignCreate):
    return await campaign_service.upload_campaign(campaign)
```

In `app/main.py`, register the limiter on the app:
```python
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from app.routers.campaign_router import limiter

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
```

---

### Task 5.3 — Add `/health` endpoint to `app/main.py`

Add this route (UptimeRobot will ping it every 5 minutes):
```python
@app.get("/health")
async def health_check():
    return {"status": "ok"}
```

---

## Final checklist — agent must verify before finishing

- [ ] No file contains `import requests` anywhere
- [ ] No file contains `with UnitOfWork()` — all converted to `async with`
- [ ] No file contains `self.cursor` in any repo class
- [ ] All repo methods are `async def`
- [ ] All SQL strings use `:param_name` style, no `?` remaining
- [ ] `backend.py` does not exist
- [ ] `requirements.txt` contains: `httpx`, `sqlalchemy[asyncio]`, `asyncpg`, `alembic`, `sentry-sdk[fastapi]`, `slowapi`
- [ ] `alembic/` directory exists with `env.py` reading `DATABASE_URL` from environment
- [ ] `alembic/versions/001_initial_schema.py` exists with all three tables
- [ ] `app/config.py` has `CALLBACK_BASE_URL`, `DATABASE_URL`, `SENTRY_DSN`
- [ ] `/health` endpoint exists in `app/main.py`
- [ ] `orphan_cleanup_loop` task is started in `startup_event`
- [ ] Sentry init is gated behind `if settings.SENTRY_DSN` so local dev without DSN doesn't crash

---

## What is handled externally (do NOT implement these)

The following are done outside this repo by the developer simultaneously:

- Supabase project creation and `DATABASE_URL` provisioning
- Upstash Redis creation and `REDIS_BROKER_URL` / `REDIS_BACKEND_URL` provisioning
- Sentry project creation and `SENTRY_DSN` provisioning
- Render environment variable configuration
- Running `alembic upgrade head` via Render shell after deploy
- UptimeRobot monitor setup pointing at `/health`
- Netlify deploy of `index.html` with updated `API_BASE`
- Exotel configuration (unchanged)