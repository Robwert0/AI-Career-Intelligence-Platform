import sys
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))

from make_admin import set_admin_flag  # noqa: E402


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
