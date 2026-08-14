import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import RefreshToken, User
from app.repositories import RefreshTokenRepository


async def make_user(db_session: AsyncSession) -> User:
    user = User(email=f"{uuid.uuid4()}@test.dev", hashed_password="not-a-real-hash")
    db_session.add(user)
    await db_session.flush()
    return user


def in_days(days: int) -> datetime:
    return datetime.now(UTC) + timedelta(days=days)


async def test_a_new_row_is_unused_and_unrevoked(db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    token = RefreshToken(
        user_id=user.id,
        family_id=uuid.uuid4(),
        token_hash="a" * 64,
        expires_at=in_days(7),
    )
    db_session.add(token)
    await db_session.flush()

    assert token.id is not None
    assert token.used_at is None
    assert token.revoked_at is None
    assert token.created_at is not None


async def test_token_hash_is_unique(db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    for _ in range(2):
        db_session.add(
            RefreshToken(
                user_id=user.id,
                family_id=uuid.uuid4(),
                token_hash="b" * 64,
                expires_at=in_days(7),
            )
        )

    with pytest.raises(IntegrityError):
        await db_session.flush()


async def add_token(
    db_session: AsyncSession,
    user: User,
    *,
    family_id: uuid.UUID | None = None,
    token_hash: str | None = None,
    expires_at: datetime | None = None,
    used_at: datetime | None = None,
    revoked_at: datetime | None = None,
) -> RefreshToken:
    token = RefreshToken(
        user_id=user.id,
        family_id=family_id or uuid.uuid4(),
        token_hash=token_hash or uuid.uuid4().hex * 2,
        expires_at=expires_at or in_days(7),
        used_at=used_at,
        revoked_at=revoked_at,
    )
    db_session.add(token)
    await db_session.flush()
    return token


async def test_create_persists_a_usable_row(db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    repo = RefreshTokenRepository(db_session)
    family_id = uuid.uuid4()

    token = await repo.create(
        user_id=user.id, family_id=family_id, token_hash="c" * 64, expires_at=in_days(7)
    )

    assert token.id is not None
    assert token.family_id == family_id
    assert await repo.get_by_hash("c" * 64) is not None


async def test_consume_returns_the_row_and_stamps_used_at(db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    repo = RefreshTokenRepository(db_session)
    token = await add_token(db_session, user, token_hash="d" * 64)

    consumed = await repo.consume("d" * 64)

    assert consumed is not None
    assert consumed.id == token.id
    assert consumed.used_at is not None


async def test_consume_is_single_use(db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    repo = RefreshTokenRepository(db_session)
    await add_token(db_session, user, token_hash="e" * 64)

    assert await repo.consume("e" * 64) is not None
    assert await repo.consume("e" * 64) is None


async def test_consume_rejects_a_revoked_token(db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    repo = RefreshTokenRepository(db_session)
    await add_token(db_session, user, token_hash="f" * 64, revoked_at=datetime.now(UTC))

    assert await repo.consume("f" * 64) is None


async def test_consume_rejects_an_expired_token(db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    repo = RefreshTokenRepository(db_session)
    await add_token(db_session, user, token_hash="1" * 64, expires_at=in_days(-1))

    assert await repo.consume("1" * 64) is None


async def test_consume_rejects_an_unknown_token(db_session: AsyncSession) -> None:
    repo = RefreshTokenRepository(db_session)

    assert await repo.consume("2" * 64) is None


async def test_revoke_family_hits_every_row_in_that_family_only(
    db_session: AsyncSession,
) -> None:
    user = await make_user(db_session)
    repo = RefreshTokenRepository(db_session)
    doomed = uuid.uuid4()
    parent = await add_token(db_session, user, family_id=doomed, used_at=datetime.now(UTC))
    child = await add_token(db_session, user, family_id=doomed)
    bystander = await add_token(db_session, user)

    await repo.revoke_family(doomed)

    # refresh, not expire_all: a bare read of an expired attribute does lazy IO,
    # which an async session cannot do outside an await.
    for token in (parent, child, bystander):
        await db_session.refresh(token)

    assert parent.revoked_at is not None
    assert child.revoked_at is not None
    assert bystander.revoked_at is None
