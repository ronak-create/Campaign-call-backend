from sqlalchemy import text


class CampaignRepository:

    def __init__(self, conn):
        self.conn = conn

    async def increment_completed(self, campaign_id: str):
        await self.conn.execute(text("""
                UPDATE campaigns
                SET completed_calls = completed_calls + 1
                WHERE id = :campaign_id
            """), {"campaign_id": campaign_id})

    async def increment_failed(self, campaign_id: str):
        await self.conn.execute(text("""
                UPDATE campaigns
                SET failed_calls = failed_calls + 1
                WHERE id = :campaign_id
            """), {"campaign_id": campaign_id})

    async def create_campaign(self, campaign_id, name, created_at, total_calls):
        await self.conn.execute(text("""
                INSERT INTO campaigns (id, name, created_at, total_calls, status)
                VALUES (:campaign_id, :name, :created_at, :total_calls, 'pending')
            """), {"campaign_id": campaign_id, "name": name, "created_at": created_at, "total_calls": total_calls})

    async def update_status(self, campaign_id, status):
        await self.conn.execute(text("""
                UPDATE campaigns
                SET status = :status
                WHERE id = :campaign_id
            """), {"status": status, "campaign_id": campaign_id})

    async def exists(self, campaign_id):
        result = await self.conn.execute(text("SELECT id FROM campaigns WHERE id = :campaign_id"), {"campaign_id": campaign_id})
        return result.fetchone() is not None

    async def delete(self, campaign_id):
        await self.conn.execute(text("DELETE FROM campaigns WHERE id = :campaign_id"), {"campaign_id": campaign_id})

    async def list_all(self):
        result = await self.conn.execute(text("""
                SELECT c.*, cs.is_running
                FROM campaigns c
                LEFT JOIN campaign_state cs ON c.id = cs.campaign_id
                ORDER BY c.created_at DESC
            """))
        return [dict(row._mapping) for row in result.fetchall()]

    async def mark_paused(self, campaign_id: str):
        await self.conn.execute(text("""
                UPDATE campaigns
                SET status = 'paused'
                WHERE id = :campaign_id
            """), {"campaign_id": campaign_id})

    async def list_with_state(self):
        result = await self.conn.execute(text("""
                SELECT c.*, cs.is_running
                FROM campaigns c
                LEFT JOIN campaign_state cs
                    ON c.id = cs.campaign_id
                ORDER BY c.created_at DESC
            """))
        return [dict(row._mapping) for row in result.fetchall()]

    async def get_by_id(self, campaign_id: str):
        result = await self.conn.execute(text(
                "SELECT * FROM campaigns WHERE id = :campaign_id"
            ), {"campaign_id": campaign_id})
        row = result.fetchone()
        return dict(row._mapping) if row else None
