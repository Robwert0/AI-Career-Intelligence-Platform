import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.schemas.auth import UserRole


class AdminUserRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    company: str | None
    role: UserRole | None
    created_at: datetime
    last_active_at: datetime | None


class AdminUsersPage(BaseModel):
    items: list[AdminUserRow]
    total: int
    by_role: dict[str, int]
    limit: int
    offset: int
    last_purge_at: datetime | None
