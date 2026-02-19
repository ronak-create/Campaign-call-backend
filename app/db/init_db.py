from app.db.database import get_db
from app.config import settings

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
                conversation_id TEXT,
                duration INTEGER,
                error_message TEXT,
                retry_count INTEGER DEFAULT 0,
                preferred_city TEXT,
                interested TEXT,
                transcript TEXT,
                analysis_status TEXT DEFAULT 'pending',
                FOREIGN KEY (campaign_id) REFERENCES campaigns(id)
            )
        ''')
        
        # Campaign state table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS campaign_state (
                campaign_id TEXT PRIMARY KEY,
                is_running INTEGER DEFAULT 0,
                current_index INTEGER DEFAULT 0,
                analysis_status TEXT DEFAULT 'not_started',
                last_updated TEXT,
                FOREIGN KEY (campaign_id) REFERENCES campaigns(id)
            )
        ''')
        
        conn.commit()
        print(f"✓ Database initialized at {settings.DB_PATH}")