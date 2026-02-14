class CallRepository:
    
    def __init__(self, conn):
        self.conn = conn
        self.cursor = conn.cursor()
        
    def mark_calling(self, call_id: int, timestamp: str):
        self.cursor.execute("""
            UPDATE calls
            SET status = 'calling',
                timestamp = ?
            WHERE id = ?
        """, (timestamp, call_id))


    def save_call_sid(self, call_id: int, call_sid: str): 
        self.cursor.execute("""
            UPDATE calls
            SET call_sid = ?
            WHERE id = ?
        """, (call_sid, call_id))

    def mark_failed(self, call_id: int, error_msg: str, timestamp: str):
            self.cursor.execute("""
                UPDATE calls
                SET status = 'failed',
                    error_message = ?,
                    retry_count = retry_count + 1,
                    timestamp = ?
                WHERE id = ?
            """, (error_msg, timestamp, call_id))

    def update_after_fetch(self, call_id: int, status: str, duration: int, recording_url: str, timestamp: str):
            self.cursor.execute("""
                UPDATE calls
                SET status = ?,
                    duration = ?,
                    recording_url = ?,
                    timestamp = ?
                WHERE id = ?
            """, (status, duration, recording_url, timestamp, call_id))

    def insert_calls_bulk(self, campaign_id, calls):
            for call in calls:
                self.cursor.execute("""
                    INSERT INTO calls (campaign_id, name, phone, status, feedback, timestamp, recording_url)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    campaign_id,
                    call.name,
                    call.phone,
                    call.status,
                    call.feedback,
                    call.timestamp,
                    call.recording_url
                ))

    def get_next_pending_call(self, campaign_id):
            self.cursor.execute("""
                SELECT * FROM calls
                WHERE campaign_id = ? AND status = 'pending'
                ORDER BY id ASC
                LIMIT 1
            """, (campaign_id,))
            row = self.cursor.fetchone()
            return dict(row) if row else None

    def mark_bot_connected(self, call_sid: str, conversation_id: str):
            self.cursor.execute("""
                UPDATE calls
                SET status = 'bot_connected',
                    conversation_id = COALESCE(conversation_id, ?)
                WHERE call_sid = ?
            """, (
                conversation_id,
                call_sid
            ))

    def exists_by_conversation(self, conversation_id: str):
     
            self.cursor.execute(
                "SELECT id FROM calls WHERE conversation_id = ?",
                (conversation_id,)
            )
        
            return self.cursor.fetchone() is not None


    def update_justification_and_interest(self, conversation_id: str, preferred_city: str, justification: str, interested: str):
            self.cursor.execute("""
                UPDATE calls
                SET feedback = COALESCE(feedback, '') || ?,
                    interested = ?,
                    preferred_city = COALESCE(preferred_city, ?)
                WHERE conversation_id = ?
            """, (
                justification,
                interested,
                preferred_city,
                conversation_id
            ))

    # ---------- SESSION END ----------

    def get_status_by_sid(self, call_sid: str):
        
            
            self.cursor.execute(
                "SELECT status FROM calls WHERE call_sid = ?",
                (call_sid,)
            )
            return self.cursor.fetchone()

    def mark_session_end(self, call_sid: str, new_status: str, duration: int):
            self.cursor.execute("""
                UPDATE calls
                SET status = ?,
                    duration = ?
                WHERE call_sid = ?
            """, (
                new_status,
                duration,
                call_sid
            ))
    
    def get_call_status_and_campaign(self, call_sid: str):
            self.cursor.execute(
                "SELECT status, campaign_id FROM calls WHERE call_sid = ?",
                (call_sid,)
            )
            return self.cursor.fetchone()


    def update_status_from_callback(
        self,
        call_sid: str,
        final_status: str,
        recording_url: str,
        timestamp: str
    ):
            self.cursor.execute("""
                UPDATE calls
                SET status = ?,
                    recording_url = COALESCE(?, recording_url),
                    timestamp = ?
                WHERE call_sid = ?
            """, (
                final_status,
                recording_url,
                timestamp,
                call_sid
            ))

    def update_preferred_city(self, call_sid: str, city: str):
            self.cursor.execute("""
                UPDATE calls
                SET preferred_city = COALESCE(preferred_city, ?)
                WHERE call_sid = ?
            """, (city, call_sid))


    def get_status_by_sid(self, call_sid: str):
            self.cursor.execute(
                "SELECT status FROM calls WHERE call_sid = ?",
                (call_sid,)
            )
            return self.cursor.fetchone()


    def mark_bot_connected_if_needed(self, call_sid: str):
            self.cursor.execute("""
                UPDATE calls
                SET status = 'bot_connected'
                WHERE call_sid = ?
                AND status NOT IN (
                    'bot_connected',
                    'user_connected',
                    'completed',
                    'failed',
                    'missed',
                    'rejected',
                    'bot_end',
                    'user_end'
                )
            """, (call_sid))
    

    def get_by_campaign(self, campaign_id: str):
            self.cursor.execute("""
                SELECT * FROM calls
                WHERE campaign_id = ?
                ORDER BY id ASC
            """, (campaign_id,))
            return [dict(row) for row in self.cursor.fetchall()]

    def get_campaign_stats(self, campaign_id: str):
            self.cursor.execute("""
                SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS completed,
                    SUM(CASE WHEN status IN ('failed','missed','rejected') THEN 1 ELSE 0 END) AS failed,
                    SUM(CASE WHEN status IN ('pending','calling','bot_connected','user_connected') THEN 1 ELSE 0 END) AS pending,
                    SUM(CASE 
                        WHEN status IN ('completed','failed','missed','rejected','bot_end','user_end')
                        THEN 1 ELSE 0 
                    END) AS done
                FROM calls
                WHERE campaign_id = ?
            """, (campaign_id,))
            return dict(self.cursor.fetchone())
    
    def get_by_id(self, call_id: int):
        self.cursor.execute(
            "SELECT * FROM calls WHERE id = ?",
            (call_id,)
        )
        row = self.cursor.fetchone()
        return dict(row) if row else None


    def delete_by_campaign(self, campaign_id: str):
            self.cursor.execute("DELETE FROM calls WHERE campaign_id = ?", (campaign_id,))

    def get_all_pending(self, campaign_id):
        self.cursor.execute("""
            SELECT * FROM calls
            WHERE campaign_id = ?
            AND status = 'pending'
            ORDER BY id ASC
        """, (campaign_id,))
        return [dict(row) for row in self.cursor.fetchall()]

    def count_pending(self, campaign_id):
        self.cursor.execute("""
            SELECT COUNT(*) as count
            FROM calls
            WHERE campaign_id = ?
            AND status = 'pending'
        """, (campaign_id,))
        row = self.cursor.fetchone()
        return row["count"]
