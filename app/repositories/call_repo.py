from sqlalchemy import text


class CallRepository:

    def __init__(self, conn):
        self.conn = conn

    async def mark_calling(self, call_id: int, timestamp: str):
        await self.conn.execute(text("""
            UPDATE calls
            SET status = 'calling',
                timestamp = :timestamp
            WHERE id = :id
        """), {"timestamp": timestamp, "id": call_id})

    async def save_call_sid(self, call_id: int, call_sid: str):
        await self.conn.execute(text("""
            UPDATE calls
            SET call_sid = :call_sid
            WHERE id = :id
        """), {"call_sid": call_sid, "id": call_id})

    async def mark_failed(self, call_id: int, error_msg: str, timestamp: str):
        await self.conn.execute(text("""
            UPDATE calls
            SET status = 'failed',
                error_message = :error_msg,
                retry_count = retry_count + 1,
                timestamp = :timestamp
            WHERE id = :id
        """), {"error_msg": error_msg, "timestamp": timestamp, "id": call_id})

    async def update_after_fetch(self, call_id: int, status: str, duration: int, recording_url: str, timestamp: str):
        await self.conn.execute(text("""
            UPDATE calls
            SET status = :status,
                duration = :duration,
                recording_url = :recording_url,
                timestamp = :timestamp
            WHERE id = :id
        """), {"status": status, "duration": duration, "recording_url": recording_url, "timestamp": timestamp, "id": call_id})

    async def insert_calls_bulk(self, campaign_id, calls):
        for call in calls:
            await self.conn.execute(text("""
                INSERT INTO calls (campaign_id, name, phone, status, feedback, timestamp, recording_url)
                VALUES (:campaign_id, :name, :phone, :status, :feedback, :timestamp, :recording_url)
            """), {
                "campaign_id": campaign_id,
                "name": call.name,
                "phone": call.phone,
                "status": call.status,
                "feedback": call.feedback,
                "timestamp": call.timestamp,
                "recording_url": call.recording_url
            })

    async def get_next_pending_call(self, campaign_id):
        result = await self.conn.execute(text("""
            SELECT * FROM calls
            WHERE campaign_id = :campaign_id AND status = 'pending'
            ORDER BY id ASC
            LIMIT 1
        """), {"campaign_id": campaign_id})
        row = result.fetchone()
        return dict(row._mapping) if row else None

    async def mark_bot_connected(self, call_sid: str, conversation_id: str):
        await self.conn.execute(text("""
            UPDATE calls
            SET status = 'bot_connected',
                conversation_id = COALESCE(conversation_id, :conversation_id)
            WHERE call_sid = :call_sid
        """), {"conversation_id": conversation_id, "call_sid": call_sid})

    async def exists_by_conversation(self, conversation_id: str):
        result = await self.conn.execute(text(
            "SELECT id FROM calls WHERE conversation_id = :conversation_id"
        ), {"conversation_id": conversation_id})
        return result.fetchone() is not None

    async def update_justification_and_interest(self, conversation_id: str, preferred_city: str, justification: str, interested: str):
        await self.conn.execute(text("""
            UPDATE calls
            SET feedback = COALESCE(feedback, '') || :justification,
                interested = :interested,
                preferred_city = COALESCE(preferred_city, :preferred_city)
            WHERE conversation_id = :conversation_id
        """), {
            "justification": justification,
            "interested": interested,
            "preferred_city": preferred_city,
            "conversation_id": conversation_id
        })

    # ---------- SESSION END ----------

    async def mark_session_end(self, call_sid: str, new_status: str, duration: int):
        await self.conn.execute(text("""
            UPDATE calls
            SET status = :new_status,
                duration = :duration
            WHERE call_sid = :call_sid
        """), {"new_status": new_status, "duration": duration, "call_sid": call_sid})

    async def get_call_status_and_campaign(self, call_sid: str):
        result = await self.conn.execute(text(
            "SELECT status, campaign_id FROM calls WHERE call_sid = :call_sid"
        ), {"call_sid": call_sid})
        return result.fetchone()

    async def update_status_from_callback(
        self,
        call_sid: str,
        final_status: str,
        recording_url: str,
        timestamp: str
    ):
        await self.conn.execute(text("""
            UPDATE calls
            SET status = :final_status,
                recording_url = COALESCE(:recording_url, recording_url),
                timestamp = :timestamp
            WHERE call_sid = :call_sid
        """), {
            "final_status": final_status,
            "recording_url": recording_url,
            "timestamp": timestamp,
            "call_sid": call_sid
        })

    async def update_preferred_city(self, call_sid: str, city: str):
        await self.conn.execute(text("""
            UPDATE calls
            SET preferred_city = COALESCE(preferred_city, :city)
            WHERE call_sid = :call_sid
        """), {"city": city, "call_sid": call_sid})

    async def get_status_by_sid(self, call_sid: str):
        result = await self.conn.execute(text(
            "SELECT status FROM calls WHERE call_sid = :call_sid"
        ), {"call_sid": call_sid})
        return result.fetchone()

    async def mark_bot_connected_if_needed(self, call_sid: str):
        await self.conn.execute(text("""
            UPDATE calls
            SET status = 'bot_connected'
            WHERE call_sid = :call_sid
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
        """), {"call_sid": call_sid})

    async def get_by_campaign(self, campaign_id: str):
        result = await self.conn.execute(text("""
            SELECT * FROM calls
            WHERE campaign_id = :campaign_id
            ORDER BY id ASC
        """), {"campaign_id": campaign_id})
        return [dict(row._mapping) for row in result.fetchall()]

    async def get_campaign_stats(self, campaign_id: str):
        result = await self.conn.execute(text("""
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS completed,
                SUM(CASE WHEN status IN ('failed','missed','rejected') THEN 1 ELSE 0 END) AS failed,
                SUM(CASE WHEN status IN ('pending','calling','bot_connected','user_connected') THEN 1 ELSE 0 END) AS pending,
                SUM(CASE
                    WHEN status IN ('completed','failed','missed','rejected','bot_end','user_end')
                    THEN 1 ELSE 0
                END) AS done,
                (SELECT analysis_status FROM campaign_state WHERE campaign_id = :campaign_id) AS analysis_status
            FROM calls
            WHERE campaign_id = :campaign_id
        """), {"campaign_id": campaign_id})
        return dict(result.fetchone()._mapping)

    async def get_by_id(self, call_id: int):
        result = await self.conn.execute(text(
            "SELECT * FROM calls WHERE id = :id"
        ), {"id": call_id})
        row = result.fetchone()
        return dict(row._mapping) if row else None

    async def delete_by_campaign(self, campaign_id: str):
        await self.conn.execute(text("DELETE FROM calls WHERE campaign_id = :campaign_id"), {"campaign_id": campaign_id})

    async def get_all_pending(self, campaign_id):
        result = await self.conn.execute(text("""
            SELECT * FROM calls
            WHERE campaign_id = :campaign_id
            AND status = 'pending'
            ORDER BY id ASC
        """), {"campaign_id": campaign_id})
        return [dict(row._mapping) for row in result.fetchall()]

    async def count_pending(self, campaign_id):
        result = await self.conn.execute(text("""
            SELECT COUNT(*) as count
            FROM calls
            WHERE campaign_id = :campaign_id
            AND status = 'pending'
        """), {"campaign_id": campaign_id})
        row = result.fetchone()
        return row._mapping["count"]

    async def update_transcript(self, call_sid: str, transcript: str):
        await self.conn.execute(text("""
            UPDATE calls
            SET transcript = :transcript, analysis_status = 'pending'
            WHERE call_sid = :call_sid
        """), {"transcript": transcript, "call_sid": call_sid})

    async def mark_call_analysis_failed(self, call_sid: str, error: str):
        await self.conn.execute(text("""
            UPDATE calls
            SET analysis_status = 'failed',
                error_message = :error
            WHERE call_sid = :call_sid
        """), {"error": error, "call_sid": call_sid})

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
