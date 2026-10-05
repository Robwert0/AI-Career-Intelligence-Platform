from typing import get_args

from app.core.retention_marker import RetentionMarker
from app.repositories import UserRepository
from app.schemas.admin import AdminUserRow, AdminUsersPage
from app.schemas.auth import UserRole

UNSPECIFIED = "unspecified"


class AdminService:
    def __init__(self, repo: UserRepository, marker: RetentionMarker) -> None:
        self._repo = repo
        self._marker = marker

    async def list_users(self, limit: int, offset: int) -> AdminUsersPage:
        users = await self._repo.list_users(limit, offset)
        counts = await self._repo.count_by_role()
        by_role = {role: counts.get(role, 0) for role in get_args(UserRole)}
        by_role[UNSPECIFIED] = counts.get(None, 0)
        return AdminUsersPage(
            items=[AdminUserRow.model_validate(user) for user in users],
            total=await self._repo.count_users(),
            by_role=by_role,
            limit=limit,
            offset=offset,
            last_purge_at=await self._marker.last_purge_at(),
        )
