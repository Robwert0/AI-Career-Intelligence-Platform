import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.security import generate_refresh_token, hash_refresh_token
from app.models import RefreshToken
from app.repositories import RefreshTokenRepository, UserRepository
from app.services.auth_service import AuthService, InvalidRefreshTokenError


def service(session: AsyncSession) -> AuthService:
    return AuthService(UserRepository(session), RefreshTokenRepository(session))


async def test_concurrent_rotation_cannot_escape_family_revocation() -> None:
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    family_id = uuid.uuid4()

    try:
        async with sessions() as session:
            user = await UserRepository(session).create_user(
                email=f"concurrent-{family_id}@test.dev", hashed_password="not-a-real-hash"
            )
            parent_raw = generate_refresh_token()
            await RefreshTokenRepository(session).create(
                user_id=user.id,
                family_id=family_id,
                token_hash=hash_refresh_token(parent_raw),
                expires_at=datetime.now(UTC) + timedelta(days=7),
            )
            await session.commit()

        async with sessions() as session:
            _, child_raw = await service(session).refresh(parent_raw)
            await session.commit()

        async def rotate_the_child() -> None:
            async with sessions() as session:
                try:
                    await service(session).refresh(child_raw)
                except InvalidRefreshTokenError:
                    return
                await session.commit()

        async def replay_the_parent() -> None:
            async with sessions() as session:
                with pytest.raises(InvalidRefreshTokenError):
                    await service(session).refresh(parent_raw)

        await asyncio.gather(rotate_the_child(), replay_the_parent())

        async with sessions() as session:
            result = await session.execute(
                select(RefreshToken).where(RefreshToken.family_id == family_id)
            )
            rows = list(result.scalars().all())

        assert rows
        assert all(row.revoked_at is not None for row in rows), (
            "a token survived revocation of its own family"
        )
    finally:
        async with engine.begin() as conn:
            await conn.execute(text("truncate refresh_tokens, users cascade"))
        await engine.dispose()
