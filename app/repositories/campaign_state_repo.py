class CampaignStateRepository:
    def __init__(self, conn):
        self.conn = conn
        self.cursor = conn.cursor()

    def initialize(self, campaign_id, created_at):
        self.cursor.execute("""
            INSERT INTO campaign_state
            (campaign_id, is_running, current_index, last_updated)
            VALUES (?, 0, 0, ?)
        """, (campaign_id, created_at))

    def set_running(self, campaign_id, value: bool):
        self.cursor.execute("""
            UPDATE campaign_state
            SET is_running = ?, last_updated = CURRENT_TIMESTAMP
            WHERE campaign_id = ?
        """, (1 if value else 0, campaign_id))

    def is_running(self, campaign_id):
        self.cursor.execute("""
            SELECT is_running FROM campaign_state
            WHERE campaign_id = ?
        """, (campaign_id,))
        row = self.cursor.fetchone()
        return row and row["is_running"]

    def get_running_campaigns(self):
        self.cursor.execute("""
            SELECT campaign_id FROM campaign_state
            WHERE is_running = 1
        """)
        return self.cursor.fetchall()

    def delete(self, campaign_id):
        self.cursor.execute(
            "DELETE FROM campaign_state WHERE campaign_id = ?",
            (campaign_id,)
        )

    def pause(self, campaign_id: str):
        self.cursor.execute("""
            UPDATE campaign_state
            SET is_running = 0,
                last_updated = CURRENT_TIMESTAMP
            WHERE campaign_id = ?
        """, (campaign_id,))

    def get_state(self, campaign_id: str):
        self.cursor.execute(
            "SELECT * FROM campaign_state WHERE campaign_id = ?",
            (campaign_id,)
        )
        row = self.cursor.fetchone()
        return dict(row) if row else None
    
    def get_analysis_status(self, campaign_id: str):
        self.cursor.execute("""
            SELECT analysis_status FROM campaign_state
            WHERE campaign_id = ?
        """, (campaign_id,))
        row = self.cursor.fetchone()
        return row["analysis_status"] if row else None
    
    def get_analysis_status_and_calls(self, campaign_id: str):
        self.cursor.execute("""
            SELECT cs.analysis_status, COUNT(c.id) as total_calls
            FROM campaign_state cs
            LEFT JOIN calls c ON cs.campaign_id = c.campaign_id
            WHERE cs.campaign_id = ?
            GROUP BY cs.campaign_id
        """, (campaign_id,))
        row = self.cursor.fetchone()
        return dict(row) if row else None
    
    def get_calls_for_analysis(self, campaign_id: str):
        self.cursor.execute("""
            SELECT *
            FROM calls
            WHERE campaign_id = ?
            AND transcript IS NOT NULL
            AND analysis_status = 'pending'
        """, (campaign_id,))
        return self.cursor.fetchall()

    def update_analysis_status(self, campaign_id: str, status: str):
        self.cursor.execute("""
            UPDATE campaign_state
            SET analysis_status = ?, last_updated = CURRENT_TIMESTAMP
            WHERE campaign_id = ?
        """, (status, campaign_id))
    
    def update_analysis_result(self, call_sid: str, city: str, interest: str, outcome: str):
        self.cursor.execute("""
            UPDATE calls
            SET preferred_city = ?,
                interested = ?,
                feedback = ?,
                analysis_status = 'completed'
            WHERE call_sid = ?
        """, (city, interest, outcome, call_sid))
