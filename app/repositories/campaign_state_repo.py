from sqlalchemy import text


class CampaignStateRepository:
    def __init__(self, conn):
        self.conn = conn

    async def initialize(self, campaign_id, created_at):
        await self.conn.execute(text("""
            INSERT INTO campaign_state
            (campaign_id, is_running, current_index, last_updated)
            VALUES (:campaign_id, 0, 0, :created_at)
        """), {"campaign_id": campaign_id, "created_at": created_at})

    async def set_running(self, campaign_id, value: bool):
        await self.conn.execute(text("""
            UPDATE campaign_state
            SET is_running = :is_running, last_updated = CURRENT_TIMESTAMP
            WHERE campaign_id = :campaign_id
        """), {"is_running": 1 if value else 0, "campaign_id": campaign_id})

    async def is_running(self, campaign_id):
        result = await self.conn.execute(text("""
            SELECT is_running FROM campaign_state
            WHERE campaign_id = :campaign_id
        """), {"campaign_id": campaign_id})
        row = result.fetchone()
        return row and row._mapping["is_running"]

    async def get_running_campaigns(self):
        result = await self.conn.execute(text("""
            SELECT campaign_id FROM campaign_state
            WHERE is_running = 1
        """))
        return result.fetchall()

    async def delete(self, campaign_id):
        await self.conn.execute(text(
            "DELETE FROM campaign_state WHERE campaign_id = :campaign_id"
        ), {"campaign_id": campaign_id})

    async def pause(self, campaign_id: str):
        await self.conn.execute(text("""
            UPDATE campaign_state
            SET is_running = 0,
                last_updated = CURRENT_TIMESTAMP
            WHERE campaign_id = :campaign_id
        """), {"campaign_id": campaign_id})

    async def get_state(self, campaign_id: str):
        result = await self.conn.execute(text(
            "SELECT * FROM campaign_state WHERE campaign_id = :campaign_id"
        ), {"campaign_id": campaign_id})
        row = result.fetchone()
        return dict(row._mapping) if row else None

    async def get_analysis_status(self, campaign_id: str):
        result = await self.conn.execute(text("""
            SELECT analysis_status FROM campaign_state
            WHERE campaign_id = :campaign_id
        """), {"campaign_id": campaign_id})
        row = result.fetchone()
        return row._mapping["analysis_status"] if row else None

    async def get_analysis_status_and_calls(self, campaign_id: str):
        result = await self.conn.execute(text("""
            SELECT cs.analysis_status, COUNT(c.id) as total_calls
            FROM campaign_state cs
            LEFT JOIN calls c ON cs.campaign_id = c.campaign_id
            WHERE cs.campaign_id = :campaign_id
            GROUP BY cs.campaign_id
        """), {"campaign_id": campaign_id})
        row = result.fetchone()
        return dict(row._mapping) if row else None

    async def get_calls_for_analysis(self, campaign_id: str):
        result = await self.conn.execute(text("""
            SELECT *
            FROM calls
            WHERE campaign_id = :campaign_id
            AND transcript IS NOT NULL
            AND analysis_status = 'pending'
        """), {"campaign_id": campaign_id})
        return result.fetchall()

    async def update_analysis_status(self, campaign_id: str, status: str):
        await self.conn.execute(text("""
            UPDATE campaign_state
            SET analysis_status = :status, last_updated = CURRENT_TIMESTAMP
            WHERE campaign_id = :campaign_id
        """), {"status": status, "campaign_id": campaign_id})

    async def update_analysis_result(self, call_sid: str, city: str, interest: str, outcome: str):
        await self.conn.execute(text("""
            UPDATE calls
            SET preferred_city = :city,
                interested = :interest,
                feedback = :outcome,
                analysis_status = 'completed'
            WHERE call_sid = :call_sid
        """), {"city": city, "interest": interest, "outcome": outcome, "call_sid": call_sid})
