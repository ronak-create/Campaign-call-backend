from app.db.database import get_db
from app.repositories.campaign_repo import CampaignRepository
from app.repositories.call_repo import CallRepository
from app.repositories.campaign_state_repo import CampaignStateRepository

class UnitOfWork:

    def __enter__(self):
        self.conn_ctx = get_db()
        self.conn = self.conn_ctx.__enter__()
        self.cursor = self.conn.cursor()

        # Pass SAME connection to repos
        self.campaigns = CampaignRepository(self.conn)
        self.calls = CallRepository(self.conn)
        self.states = CampaignStateRepository(self.conn)

        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type:
            self.conn.rollback()
        else:
            self.conn.commit()

        self.conn_ctx.__exit__(exc_type, exc, tb)
