from datetime import datetime, timedelta

from app.core.config import settings
from app.repositories import UserRepository


class RetentionService:
    def __init__(self, repo: UserRepository) -> None:
        self._repo = repo

    async def purge_inactive(self, now: datetime) -> int:
        cutoff = now - timedelta(days=settings.account_retention_days)
        return await self._repo.delete_inactive(cutoff)
