import asyncio
import os
import sys
import uuid
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.security import hash_password, verify_password
from app.models import User
from app.repositories import UserRepository

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))

import make_admin  # noqa: E402
from make_admin import Result, create_admin, grant_admin, revoke_admin  # noqa: E402

ADMIN_PASSWORD = "a-long-admin-pass-16"
SHORT_PASSWORD = "fifteen-chars-x"


async def _add_user(session: AsyncSession, email: str, password: str) -> User:
    user = User(email=email, hashed_password=hash_password(password))
    session.add(user)
    await session.flush()
    return user


async def test_create_makes_a_new_admin_whose_password_verifies(db_session: AsyncSession) -> None:
    outcome = await create_admin(db_session, "admin@test.dev", ADMIN_PASSWORD, ADMIN_PASSWORD)

    assert outcome.result is Result.CREATED
    user = await UserRepository(db_session).get_user_by_email("admin@test.dev")
    assert user is not None
    await db_session.refresh(user)
    assert user.id == outcome.user_id
    assert user.is_admin is True
    assert verify_password(ADMIN_PASSWORD, user.hashed_password)


async def test_create_inserts_the_admin_flag_instead_of_updating_by_email(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def no_update(self: object, email: str, value: bool) -> bool:
        raise AssertionError("create must not touch rows by email after inserting")

    monkeypatch.setattr(UserRepository, "set_admin", no_update)

    outcome = await create_admin(db_session, "admin@test.dev", ADMIN_PASSWORD, ADMIN_PASSWORD)

    assert outcome.result is Result.CREATED


async def test_create_refuses_an_existing_email_and_leaves_the_row_alone(
    db_session: AsyncSession,
) -> None:
    squatter = await _add_user(db_session, "admin@test.dev", "squatter-pass")
    original_hash = squatter.hashed_password

    outcome = await create_admin(db_session, "ADMIN@test.dev", ADMIN_PASSWORD, ADMIN_PASSWORD)

    assert outcome.result is Result.EMAIL_EXISTS
    await db_session.refresh(squatter)
    assert squatter.is_admin is False
    assert squatter.hashed_password == original_hash


async def test_create_refuses_a_password_under_16_characters(db_session: AsyncSession) -> None:
    outcome = await create_admin(db_session, "admin@test.dev", SHORT_PASSWORD, SHORT_PASSWORD)

    assert outcome.result is Result.TOO_SHORT
    assert await UserRepository(db_session).get_user_by_email("admin@test.dev") is None


async def test_create_refuses_a_password_over_the_bcrypt_limit(db_session: AsyncSession) -> None:
    too_long = "é" * 37

    outcome = await create_admin(db_session, "admin@test.dev", too_long, too_long)

    assert outcome.result is Result.TOO_LONG
    assert await UserRepository(db_session).get_user_by_email("admin@test.dev") is None


async def test_create_refuses_a_confirmation_mismatch(db_session: AsyncSession) -> None:
    outcome = await create_admin(db_session, "admin@test.dev", ADMIN_PASSWORD, ADMIN_PASSWORD + "x")

    assert outcome.result is Result.MISMATCH
    assert await UserRepository(db_session).get_user_by_email("admin@test.dev") is None


async def test_grant_refuses_a_correct_password_under_16_characters(
    db_session: AsyncSession,
) -> None:
    user = await _add_user(db_session, "robert@test.dev", SHORT_PASSWORD)

    outcome = await grant_admin(db_session, user.id, SHORT_PASSWORD, was_admin=False)

    assert outcome.result is Result.TOO_SHORT
    await db_session.refresh(user)
    assert user.is_admin is False


async def test_grant_refuses_a_wrong_password(db_session: AsyncSession) -> None:
    user = await _add_user(db_session, "robert@test.dev", "squatter-pass-long-enough")

    outcome = await grant_admin(db_session, user.id, ADMIN_PASSWORD, was_admin=False)

    assert outcome.result is Result.WRONG_PASSWORD
    await db_session.refresh(user)
    assert user.is_admin is False


async def test_grant_sets_the_flag_with_the_correct_long_password(
    db_session: AsyncSession,
) -> None:
    user = await _add_user(db_session, "robert@test.dev", ADMIN_PASSWORD)

    outcome = await grant_admin(db_session, user.id, ADMIN_PASSWORD, was_admin=False)

    assert outcome.result is Result.GRANTED
    assert outcome.user_id == user.id
    await db_session.refresh(user)
    assert user.is_admin is True


async def test_grant_refuses_when_the_row_was_replaced_during_the_prompt(
    db_session: AsyncSession,
) -> None:
    shown = await _add_user(db_session, "robert@test.dev", ADMIN_PASSWORD)
    shown_id = shown.id
    await db_session.delete(shown)
    await db_session.flush()
    squatter = await _add_user(db_session, "robert@test.dev", ADMIN_PASSWORD)

    outcome = await grant_admin(db_session, shown_id, ADMIN_PASSWORD, was_admin=False)

    assert outcome.result is Result.NO_SUCH_USER
    await db_session.refresh(squatter)
    assert squatter.is_admin is False


async def test_grant_refuses_when_the_flag_changed_during_the_prompt(
    db_session: AsyncSession,
) -> None:
    user = await _add_user(db_session, "robert@test.dev", ADMIN_PASSWORD)
    user.is_admin = True
    await db_session.flush()

    outcome = await grant_admin(db_session, user.id, ADMIN_PASSWORD, was_admin=False)

    assert outcome.result is Result.CHANGED


async def test_revoke_clears_the_flag(db_session: AsyncSession) -> None:
    user = await _add_user(db_session, "robert@test.dev", ADMIN_PASSWORD)
    user.is_admin = True
    await db_session.flush()

    outcome = await revoke_admin(db_session, "robert@test.dev")

    assert outcome.result is Result.REVOKED
    await db_session.refresh(user)
    assert user.is_admin is False


async def test_revoke_reports_an_unknown_email(db_session: AsyncSession) -> None:
    outcome = await revoke_admin(db_session, "nobody@test.dev")

    assert outcome.result is Result.NO_SUCH_USER


@dataclass
class CliDb:
    sessions: async_sessionmaker[AsyncSession]
    open_sessions: int = 0


@pytest.fixture
def cli_db(monkeypatch: pytest.MonkeyPatch) -> Iterator[CliDb]:
    # main() runs its own event loop via asyncio.run, so it needs an engine that never
    # carries a connection across loops, and the rows it commits must be cleaned up by hand.
    engine = create_async_engine(os.environ["DATABASE_URL"], poolclass=NullPool)
    db = CliDb(async_sessionmaker(engine, expire_on_commit=False))

    @asynccontextmanager
    async def tracked() -> AsyncIterator[AsyncSession]:
        db.open_sessions += 1
        try:
            async with db.sessions() as session:
                yield session
        finally:
            db.open_sessions -= 1

    monkeypatch.setattr(make_admin, "SessionLocal", tracked)
    monkeypatch.setattr(make_admin, "configure_logging", lambda level: None)
    yield db

    async def cleanup() -> None:
        async with db.sessions() as session:
            await session.execute(delete(User).where(User.email.like("%@cli.test.dev")))
            await session.commit()
        await engine.dispose()

    asyncio.run(cleanup())


def _main(monkeypatch: pytest.MonkeyPatch, db: CliDb, argv: list[str], passwords: list[str]) -> int:
    answers = iter(passwords)

    def fake_getpass(prompt: str = "") -> str:
        # A transaction held open across the prompt would pin row state for as long as it waits.
        assert db.open_sessions == 0
        return next(answers)

    monkeypatch.setattr("getpass.getpass", fake_getpass)
    monkeypatch.setattr(sys, "argv", ["make_admin.py", *argv])
    return make_admin.main()


def _cli_email() -> str:
    return f"{uuid.uuid4().hex[:12]}@cli.test.dev"


def test_main_exits_0_after_creating_an_admin(
    cli_db: CliDb, monkeypatch: pytest.MonkeyPatch
) -> None:
    email = _cli_email()

    assert _main(monkeypatch, cli_db, ["--create", email], [ADMIN_PASSWORD, ADMIN_PASSWORD]) == 0

    async def fetch() -> User | None:
        async with cli_db.sessions() as session:
            return await UserRepository(session).get_user_by_email(email)

    user = asyncio.run(fetch())
    assert user is not None
    assert user.is_admin is True


def test_main_exits_1_for_an_unknown_email(cli_db: CliDb, monkeypatch: pytest.MonkeyPatch) -> None:
    assert _main(monkeypatch, cli_db, [_cli_email()], [ADMIN_PASSWORD]) == 1


def test_main_exits_2_for_a_short_password(
    cli_db: CliDb,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert (
        _main(monkeypatch, cli_db, ["--create", _cli_email()], [SHORT_PASSWORD, SHORT_PASSWORD])
        == 2
    )
    assert "admin passwords must be at least 16 characters" in capsys.readouterr().err


def test_main_exits_3_when_the_email_already_exists(
    cli_db: CliDb,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    email = _cli_email()

    async def squat() -> None:
        async with cli_db.sessions() as session:
            await _add_user(session, email, "squatter-pass")
            await session.commit()

    asyncio.run(squat())

    assert _main(monkeypatch, cli_db, ["--create", email], [ADMIN_PASSWORD, ADMIN_PASSWORD]) == 3
    assert "an account with this email already exists" in capsys.readouterr().err


def test_main_exits_4_on_an_unexpected_error_without_leaking_the_message(
    cli_db: CliDb,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    email = _cli_email()

    def explode(password: str) -> str:
        raise RuntimeError("secret detail")

    monkeypatch.setattr(make_admin, "hash_password", explode)

    assert _main(monkeypatch, cli_db, ["--create", email], [ADMIN_PASSWORD, ADMIN_PASSWORD]) == 4
    err = capsys.readouterr().err
    assert "unexpected error: RuntimeError" in err
    assert "secret detail" not in err

    async def fetch() -> User | None:
        async with cli_db.sessions() as session:
            return await UserRepository(session).get_user_by_email(email)

    assert asyncio.run(fetch()) is None


def _seed(db: CliDb, email: str, password: str) -> None:
    async def seed() -> None:
        async with db.sessions() as session:
            await _add_user(session, email, password)
            await session.commit()

    asyncio.run(seed())


def _is_admin(db: CliDb, email: str) -> bool | None:
    async def fetch() -> bool | None:
        async with db.sessions() as session:
            user = await UserRepository(session).get_user_by_email(email)
            return None if user is None else user.is_admin

    return asyncio.run(fetch())


def test_main_grants_with_a_padded_email_and_no_transaction_across_the_prompt(
    cli_db: CliDb, monkeypatch: pytest.MonkeyPatch
) -> None:
    email = _cli_email()
    _seed(cli_db, email, ADMIN_PASSWORD)

    assert _main(monkeypatch, cli_db, [f"  {email.upper()}  "], [ADMIN_PASSWORD]) == 0
    assert _is_admin(cli_db, email) is True


def test_main_exits_2_for_an_email_the_api_would_reject(
    cli_db: CliDb, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert (
        _main(monkeypatch, cli_db, ["--create", "admin@x.local"], [ADMIN_PASSWORD, ADMIN_PASSWORD])
        == 2
    )
    assert "not a valid email address: " in capsys.readouterr().err
    assert _is_admin(cli_db, "admin@x.local") is None
