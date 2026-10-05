import importlib.util
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import RefreshToken, User

MIGRATION = (
    Path(__file__).parents[1] / "alembic" / "versions" / "7c1e5b9a2d40_backfill_last_active_at.py"
)
T0 = datetime(2026, 1, 1, tzinfo=UTC)


def load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("backfill_last_active_at", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def add_user(session: AsyncSession, last_active_at: datetime | None = None) -> User:
    user = User(
        email=f"{uuid.uuid4().hex[:12]}@test.dev",
        hashed_password="x",
        created_at=T0,
        last_active_at=last_active_at,
    )
    session.add(user)
    await session.flush()
    return user


def add_token(session: AsyncSession, user: User, created_at: datetime) -> None:
    session.add(
        RefreshToken(
            user_id=user.id,
            family_id=uuid.uuid4(),
            token_hash=uuid.uuid4().hex * 2,
            expires_at=created_at + timedelta(days=7),
            created_at=created_at,
        )
    )


async def test_the_backfill_sets_last_active_from_the_newest_refresh_token_only_when_missing(
    db_session: AsyncSession,
) -> None:
    never_set = await add_user(db_session)
    already_set = await add_user(db_session, last_active_at=T0 + timedelta(days=50))
    no_tokens = await add_user(db_session)
    add_token(db_session, never_set, T0 + timedelta(days=3))
    add_token(db_session, never_set, T0 + timedelta(days=9))
    add_token(db_session, already_set, T0 + timedelta(days=90))
    await db_session.flush()

    await db_session.execute(text(load_migration().BACKFILL_LAST_ACTIVE_SQL))

    for user in (never_set, already_set, no_tokens):
        await db_session.refresh(user)
    assert never_set.last_active_at == T0 + timedelta(days=9)
    assert already_set.last_active_at == T0 + timedelta(days=50)
    assert no_tokens.last_active_at is None
