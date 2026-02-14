class CampaignRepository:

    def __init__(self, conn):
        self.conn = conn
        self.cursor = conn.cursor()

    def increment_completed(self, campaign_id: str):
        self.cursor.execute("""
                UPDATE campaigns
                SET completed_calls = completed_calls + 1
                WHERE id = ?
            """, (campaign_id,))

    def increment_failed(self, campaign_id: str):
        self.cursor.execute("""
                UPDATE campaigns
                SET failed_calls = failed_calls + 1
                WHERE id = ?
            """, (campaign_id,))

    def create_campaign(self, campaign_id, name, created_at, total_calls):
        self.cursor.execute("""
                INSERT INTO campaigns (id, name, created_at, total_calls, status)
                VALUES (?, ?, ?, ?, 'pending')
            """, (campaign_id, name, created_at, total_calls))

    def update_status(self, campaign_id, status):
        self.cursor.execute("""
                UPDATE campaigns
                SET status = ?
                WHERE id = ?
            """, (status, campaign_id))

    def exists(self, campaign_id):
        self.cursor.execute("SELECT id FROM campaigns WHERE id = ?", (campaign_id,))
        return self.cursor.fetchone() is not None

    def delete(self, campaign_id):
        self.cursor.execute("DELETE FROM campaigns WHERE id = ?", (campaign_id,))

    def list_all(self):
        self.cursor.execute("""
                SELECT c.*, cs.is_running 
                FROM campaigns c
                LEFT JOIN campaign_state cs ON c.id = cs.campaign_id
                ORDER BY c.created_at DESC
            """)
        return [dict(row) for row in self.cursor.fetchall()]
    
    def mark_paused(self, campaign_id: str):
        self.cursor.execute("""
                UPDATE campaigns
                SET status = 'paused'
                WHERE id = ?
            """, (campaign_id,))

    def list_with_state(self):
        self.cursor.execute("""
                SELECT c.*, cs.is_running
                FROM campaigns c
                LEFT JOIN campaign_state cs
                    ON c.id = cs.campaign_id
                ORDER BY c.created_at DESC
            """)
        return [dict(row) for row in self.cursor.fetchall()]
    
    def get_by_id(self, campaign_id: str):
        self.cursor.execute(
                "SELECT * FROM campaigns WHERE id = ?",
                (campaign_id,)
            )
        row = self.cursor.fetchone()
        return dict(row) if row else None
