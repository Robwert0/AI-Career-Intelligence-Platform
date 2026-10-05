import asyncio
import os
import sys
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.models import User
from app.repositories import UserRepository

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))

import delete_account  # noqa: E402
from delete_account import Result, erase_account  # noqa: E402


async def add_user(session: AsyncSession, email: str, *, is_admin: bool = False) -> uuid.UUID:
    user = User(email=email, hashed_password="not-a-real-hash", is_admin=is_admin)
    session.add(user)
    await session.flush()
    return user.id


async def exists(session: AsyncSession, user_id: uuid.UUID) -> bool:
    return await session.scalar(select(User.id).where(User.id == user_id)) is not None


async def test_a_confirmed_erasure_deletes_the_account(db_session: AsyncSession) -> None:
    user_id = await add_user(db_session, "visitor@test.dev")

    outcome = await erase_account(db_session, "visitor@test.dev", "Visitor@test.dev ")

    assert outcome.result is Result.DELETED
    assert outcome.user_id == user_id
    assert not await exists(db_session, user_id)


async def test_an_unknown_email_is_not_found(db_session: AsyncSession) -> None:
    outcome = await erase_account(db_session, "nobody@test.dev", "nobody@test.dev")

    assert outcome.result is Result.NOT_FOUND


async def test_a_confirmation_mismatch_keeps_the_account(db_session: AsyncSession) -> None:
    user_id = await add_user(db_session, "visitor@test.dev")

    outcome = await erase_account(db_session, "visitor@test.dev", "visitor@test.de")

    assert outcome.result is Result.MISMATCH
    assert await exists(db_session, user_id)


async def test_an_admin_is_refused_without_allow_admin(db_session: AsyncSession) -> None:
    user_id = await add_user(db_session, "admin@test.dev", is_admin=True)

    outcome = await erase_account(db_session, "admin@test.dev", "admin@test.dev")

    assert outcome.result is Result.ADMIN_REFUSED
    assert await exists(db_session, user_id)


async def test_an_admin_is_deleted_with_allow_admin(db_session: AsyncSession) -> None:
    user_id = await add_user(db_session, "admin@test.dev", is_admin=True)

    outcome = await erase_account(db_session, "admin@test.dev", "admin@test.dev", allow_admin=True)

    assert outcome.result is Result.DELETED
    assert not await exists(db_session, user_id)


@pytest.fixture
def cli_db(monkeypatch: pytest.MonkeyPatch) -> Iterator[async_sessionmaker[AsyncSession]]:
    # main() runs its own event loop via asyncio.run, so it needs an engine that never
    # carries a connection across loops, and the rows it commits must be cleaned up by hand.
    engine = create_async_engine(os.environ["DATABASE_URL"], poolclass=NullPool)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(delete_account, "SessionLocal", sessions)
    monkeypatch.setattr(delete_account, "configure_logging", lambda level: None)
    yield sessions

    async def cleanup() -> None:
        async with sessions() as session:
            await session.execute(delete(User).where(User.email.like("%@erase.test.dev")))
            await session.commit()
        await engine.dispose()

    asyncio.run(cleanup())


def _seed(sessions: async_sessionmaker[AsyncSession], *, is_admin: bool = False) -> str:
    email = f"{uuid.uuid4().hex[:12]}@erase.test.dev"

    async def seed() -> None:
        async with sessions() as session:
            await add_user(session, email, is_admin=is_admin)
            await session.commit()

    asyncio.run(seed())
    return email


def _still_there(sessions: async_sessionmaker[AsyncSession], email: str) -> bool:
    async def check() -> bool:
        async with sessions() as session:
            return await session.scalar(select(User.id).where(User.email == email)) is not None

    return asyncio.run(check())


def _main(monkeypatch: pytest.MonkeyPatch, argv: list[str], typed: str) -> int:
    monkeypatch.setattr("builtins.input", lambda prompt="": typed)
    monkeypatch.setattr(sys, "argv", ["delete_account.py", *argv])
    return delete_account.main()


def test_main_exits_0_and_commits_the_deletion(
    cli_db: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    email = _seed(cli_db)

    assert _main(monkeypatch, [email], email) == 0
    assert not _still_there(cli_db, email)


def test_main_exits_1_for_an_unknown_email(
    cli_db: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    assert _main(monkeypatch, ["nobody@erase.test.dev"], "nobody@erase.test.dev") == 1


def test_main_exits_2_on_a_confirmation_mismatch(
    cli_db: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    email = _seed(cli_db)

    assert _main(monkeypatch, [email], "someone-else@erase.test.dev") == 2
    assert _still_there(cli_db, email)


def test_main_exits_3_for_an_admin_without_allow_admin(
    cli_db: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    email = _seed(cli_db, is_admin=True)

    assert _main(monkeypatch, [email], email) == 3
    assert _still_there(cli_db, email)


def test_main_exits_4_on_an_unexpected_error_and_deletes_nothing(
    cli_db: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    email = _seed(cli_db)

    async def explode(self: object, email: str) -> bool:
        raise RuntimeError(f"secret detail {email}")

    monkeypatch.setattr(UserRepository, "delete_by_email", explode)

    assert _main(monkeypatch, [email], email) == 4
    err = capsys.readouterr().err
    assert "unexpected error: RuntimeError" in err
    assert "secret detail" not in err
    assert _still_there(cli_db, email)
