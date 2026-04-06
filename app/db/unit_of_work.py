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
