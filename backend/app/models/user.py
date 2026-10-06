import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, String, func
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
)

from app.core.db import Base

USER_ROLES = ("recruiter", "hiring_manager", "engineer", "other")


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "role IN ('recruiter', 'hiring_manager', 'engineer', 'other')", name="ck_users_role"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(CITEXT, unique=True, index=True)
    hashed_password: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    company: Mapped[str | None] = mapped_column(String(100))
    role: Mapped[str | None] = mapped_column(String(20))
    is_admin: Mapped[bool] = mapped_column(default=False, server_default="false")
    last_active_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
