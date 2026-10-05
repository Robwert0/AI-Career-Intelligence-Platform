import asyncio
import logging
import os
import re
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import Settings, settings
from app.models import RefreshToken, User
from app.repositories import UserRepository
from app.services.retention_service import RetentionService
from app.workers.tasks import purge_inactive_accounts

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)
CUTOFF = NOW - timedelta(days=365)


def days_ago(days: int) -> datetime:
    return NOW - timedelta(days=days)


async def add_user(
    session: AsyncSession,
    *,
    created_days_ago: int,
    active_days_ago: int | None,
    is_admin: bool = False,
    email: str | None = None,
) -> uuid.UUID:
    user = User(
        email=email or f"{uuid.uuid4().hex[:12]}@test.dev",
        hashed_password="not-a-real-hash",
        created_at=days_ago(created_days_ago),
        last_active_at=None if active_days_ago is None else days_ago(active_days_ago),
        is_admin=is_admin,
    )
    session.add(user)
    await session.flush()
    return user.id


async def existing_ids(session: AsyncSession, ids: list[uuid.UUID]) -> set[uuid.UUID]:
    return set(await session.scalars(select(User.id).where(User.id.in_(ids))))


async def test_delete_inactive_keeps_only_recent_activity_and_admins(
    db_session: AsyncSession,
) -> None:
    inactive = await add_user(db_session, created_days_ago=800, active_days_ago=400)
    active = await add_user(db_session, created_days_ago=800, active_days_ago=10)
    never_active_old = await add_user(db_session, created_days_ago=400, active_days_ago=None)
    never_active_new = await add_user(db_session, created_days_ago=10, active_days_ago=None)
    inactive_admin = await add_user(
        db_session, created_days_ago=800, active_days_ago=400, is_admin=True
    )
    all_ids = [inactive, active, never_active_old, never_active_new, inactive_admin]

    deleted = await UserRepository(db_session).delete_inactive(CUTOFF)

    assert deleted == 2
    assert await existing_ids(db_session, all_ids) == {active, never_active_new, inactive_admin}


async def test_delete_inactive_takes_the_refresh_tokens_with_the_account(
    db_session: AsyncSession,
) -> None:
    inactive = await add_user(db_session, created_days_ago=800, active_days_ago=400)
    db_session.add(
        RefreshToken(
            user_id=inactive,
            family_id=uuid.uuid4(),
            token_hash=uuid.uuid4().hex * 2,
            expires_at=NOW + timedelta(days=7),
        )
    )
    await db_session.flush()

    await UserRepository(db_session).delete_inactive(CUTOFF)

    remaining = await db_session.scalars(
        select(RefreshToken.id).where(RefreshToken.user_id == inactive)
    )
    assert list(remaining) == []


async def test_delete_by_email_reports_whether_an_account_went(db_session: AsyncSession) -> None:
    user_id = await add_user(
        db_session, created_days_ago=10, active_days_ago=1, email="gone@test.dev"
    )
    repo = UserRepository(db_session)

    assert await repo.delete_by_email("GONE@test.dev") is True
    assert await existing_ids(db_session, [user_id]) == set()
    assert await repo.delete_by_email("gone@test.dev") is False


class RecordingRepo:
    def __init__(self) -> None:
        self.cutoffs: list[datetime] = []

    async def delete_inactive(self, cutoff: datetime) -> int:
        self.cutoffs.append(cutoff)
        return 7


async def test_the_service_cutoff_follows_the_retention_setting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "account_retention_days", 90)
    repo = RecordingRepo()

    purged = await RetentionService(repo).purge_inactive(NOW)  # type: ignore[arg-type]

    assert purged == 7
    assert repo.cutoffs == [NOW - timedelta(days=90)]


def test_retention_defaults_to_a_year_and_refuses_under_30_days(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ACCOUNT_RETENTION_DAYS", raising=False)
    assert Settings(_env_file=None).account_retention_days == 365

    monkeypatch.setenv("ACCOUNT_RETENTION_DAYS", "29")
    with pytest.raises(ValidationError, match="account_retention_days"):
        Settings(_env_file=None)


@pytest.fixture
def committed_db() -> Iterator[async_sessionmaker[AsyncSession]]:
    # The task commits through its own engine, so these rows bypass db_session's rollback.
    engine = create_async_engine(os.environ["DATABASE_URL"], poolclass=NullPool)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    yield sessions

    async def cleanup() -> None:
        async with sessions() as session:
            await session.execute(delete(User).where(User.email.like("%@purge.test.dev")))
            await session.commit()
        await engine.dispose()

    asyncio.run(cleanup())


def test_the_task_purges_and_commits_and_survives_a_second_run(
    committed_db: async_sessionmaker[AsyncSession], caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="app.workers.tasks")
    real_now = datetime.now(UTC)

    async def seed() -> tuple[uuid.UUID, uuid.UUID]:
        async with committed_db() as session:
            old = User(
                email="old@purge.test.dev",
                hashed_password="x",
                created_at=real_now - timedelta(days=800),
                last_active_at=real_now - timedelta(days=400),
            )
            fresh = User(
                email="fresh@purge.test.dev",
                hashed_password="x",
                last_active_at=real_now - timedelta(days=1),
            )
            session.add_all([old, fresh])
            await session.commit()
            return old.id, fresh.id

    old_id, fresh_id = asyncio.run(seed())

    purge_inactive_accounts()
    # A second run in the same process gets a new loop; no pooled connection may carry over.
    purge_inactive_accounts()

    async def remaining() -> set[uuid.UUID]:
        async with committed_db() as session:
            return await existing_ids(session, [old_id, fresh_id])

    assert asyncio.run(remaining()) == {fresh_id}
    messages = [record.getMessage() for record in caplog.records]
    assert any(re.fullmatch(r"purged \d+ inactive accounts", message) for message in messages)
    assert not any("@purge.test.dev" in message for message in messages)
