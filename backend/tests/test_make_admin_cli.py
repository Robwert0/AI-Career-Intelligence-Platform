import sys
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models import User

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))

from make_admin import set_admin_flag, verify_owner  # noqa: E402


async def test_grant_then_revoke(db_session: AsyncSession) -> None:
    user = User(email="robert@test.dev", hashed_password="x")
    db_session.add(user)
    await db_session.flush()

    assert await set_admin_flag(db_session, "ROBERT@test.dev", True) is True
    await db_session.refresh(user)
    assert user.is_admin is True

    assert await set_admin_flag(db_session, "robert@test.dev", False) is True
    await db_session.refresh(user)
    assert user.is_admin is False


async def test_an_unknown_email_reports_not_found(db_session: AsyncSession) -> None:
    assert await set_admin_flag(db_session, "nobody@test.dev", True) is False


async def test_the_owner_password_returns_the_account(db_session: AsyncSession) -> None:
    user = User(email="robert@test.dev", hashed_password=hash_password("owner-pass-1"))
    db_session.add(user)
    await db_session.flush()

    owner = await verify_owner(db_session, "robert@test.dev", "owner-pass-1")

    assert owner is not None
    assert owner.id == user.id


async def test_a_squatted_account_is_not_verified_with_another_password(
    db_session: AsyncSession,
) -> None:
    db_session.add(User(email="robert@test.dev", hashed_password=hash_password("squatter-pass")))
    await db_session.flush()

    assert await verify_owner(db_session, "robert@test.dev", "owner-pass-1") is None


async def test_an_unknown_email_is_not_verified(db_session: AsyncSession) -> None:
    assert await verify_owner(db_session, "nobody@test.dev", "owner-pass-1") is None
