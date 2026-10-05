import asyncio
import os
import sys
import uuid
from collections.abc import Iterator
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
from make_admin import Result, create_admin, grant_admin, revoke_admin, verify_owner  # noqa: E402

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

    outcome = await grant_admin(db_session, "robert@test.dev", SHORT_PASSWORD)

    assert outcome.result is Result.TOO_SHORT
    await db_session.refresh(user)
    assert user.is_admin is False


async def test_grant_refuses_a_wrong_password(db_session: AsyncSession) -> None:
    user = await _add_user(db_session, "robert@test.dev", "squatter-pass-long-enough")

    outcome = await grant_admin(db_session, "robert@test.dev", ADMIN_PASSWORD)

    assert outcome.result is Result.WRONG_PASSWORD
    await db_session.refresh(user)
    assert user.is_admin is False


async def test_grant_sets_the_flag_with_the_correct_long_password(
    db_session: AsyncSession,
) -> None:
    user = await _add_user(db_session, "robert@test.dev", ADMIN_PASSWORD)

    outcome = await grant_admin(db_session, "ROBERT@test.dev", ADMIN_PASSWORD)

    assert outcome.result is Result.GRANTED
    assert outcome.user_id == user.id
    await db_session.refresh(user)
    assert user.is_admin is True


async def test_grant_reports_an_unknown_email(db_session: AsyncSession) -> None:
    outcome = await grant_admin(db_session, "nobody@test.dev", ADMIN_PASSWORD)

    assert outcome.result is Result.NO_SUCH_USER


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


async def test_the_owner_password_returns_the_account(db_session: AsyncSession) -> None:
    user = await _add_user(db_session, "robert@test.dev", "owner-pass-1")

    owner = await verify_owner(db_session, "robert@test.dev", "owner-pass-1")

    assert owner is not None
    assert owner.id == user.id


async def test_a_squatted_account_is_not_verified_with_another_password(
    db_session: AsyncSession,
) -> None:
    await _add_user(db_session, "robert@test.dev", "squatter-pass")

    assert await verify_owner(db_session, "robert@test.dev", "owner-pass-1") is None


@pytest.fixture
def cli_db(monkeypatch: pytest.MonkeyPatch) -> Iterator[async_sessionmaker[AsyncSession]]:
    # main() runs its own event loop via asyncio.run, so it needs an engine that never
    # carries a connection across loops, and the rows it commits must be cleaned up by hand.
    engine = create_async_engine(os.environ["DATABASE_URL"], poolclass=NullPool)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(make_admin, "SessionLocal", sessions)
    monkeypatch.setattr(make_admin, "configure_logging", lambda level: None)
    yield sessions

    async def cleanup() -> None:
        async with sessions() as session:
            await session.execute(delete(User).where(User.email.like("%@cli.test.dev")))
            await session.commit()
        await engine.dispose()

    asyncio.run(cleanup())


def _main(monkeypatch: pytest.MonkeyPatch, argv: list[str], passwords: list[str]) -> int:
    answers = iter(passwords)
    monkeypatch.setattr("getpass.getpass", lambda prompt="": next(answers))
    monkeypatch.setattr(sys, "argv", ["make_admin.py", *argv])
    return make_admin.main()


def _cli_email() -> str:
    return f"{uuid.uuid4().hex[:12]}@cli.test.dev"


def test_main_exits_0_after_creating_an_admin(
    cli_db: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    email = _cli_email()

    assert _main(monkeypatch, ["--create", email], [ADMIN_PASSWORD, ADMIN_PASSWORD]) == 0

    async def fetch() -> User | None:
        async with cli_db() as session:
            return await UserRepository(session).get_user_by_email(email)

    user = asyncio.run(fetch())
    assert user is not None
    assert user.is_admin is True


def test_main_exits_1_for_an_unknown_email(
    cli_db: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    assert _main(monkeypatch, [_cli_email()], [ADMIN_PASSWORD]) == 1


def test_main_exits_2_for_a_short_password(
    cli_db: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert _main(monkeypatch, ["--create", _cli_email()], [SHORT_PASSWORD, SHORT_PASSWORD]) == 2
    assert "admin passwords must be at least 16 characters" in capsys.readouterr().err


def test_main_exits_3_when_the_email_already_exists(
    cli_db: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    email = _cli_email()

    async def squat() -> None:
        async with cli_db() as session:
            await _add_user(session, email, "squatter-pass")
            await session.commit()

    asyncio.run(squat())

    assert _main(monkeypatch, ["--create", email], [ADMIN_PASSWORD, ADMIN_PASSWORD]) == 3
    assert "an account with this email already exists" in capsys.readouterr().err


def test_main_exits_4_on_an_unexpected_error_without_leaking_the_message(
    cli_db: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    email = _cli_email()

    def explode(password: str) -> str:
        raise RuntimeError("secret detail")

    monkeypatch.setattr(make_admin, "hash_password", explode)

    assert _main(monkeypatch, ["--create", email], [ADMIN_PASSWORD, ADMIN_PASSWORD]) == 4
    err = capsys.readouterr().err
    assert "unexpected error: RuntimeError" in err
    assert "secret detail" not in err

    async def fetch() -> User | None:
        async with cli_db() as session:
            return await UserRepository(session).get_user_by_email(email)

    assert asyncio.run(fetch()) is None
