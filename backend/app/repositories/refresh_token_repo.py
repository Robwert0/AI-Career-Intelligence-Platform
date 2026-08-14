import uuid
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import RefreshToken


class RefreshTokenRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        user_id: uuid.UUID,
        family_id: uuid.UUID,
        token_hash: str,
        expires_at: datetime,
    ) -> RefreshToken:
        token = RefreshToken(
            user_id=user_id,
            family_id=family_id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        self._session.add(token)
        await self._session.flush()

        return token

    async def get_by_hash(self, token_hash: str) -> RefreshToken | None:
        result = await self._session.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )
        return result.scalar_one_or_none()

    async def _lock_family(self, family_id: uuid.UUID) -> None:
        # Held to end of transaction. Rotation and revocation must serialise per family:
        # a child INSERTed by an uncommitted rotation is invisible to revoke_family's
        # snapshot and takes no lock, so without this it survives its family's revocation.
        await self._session.execute(
            select(func.pg_advisory_xact_lock(func.hashtextextended(str(family_id), 0)))
        )

    async def consume(self, token_hash: str) -> RefreshToken | None:
        known = await self.get_by_hash(token_hash)
        if known is None:
            return None

        await self._lock_family(known.family_id)

        stmt = (
            update(RefreshToken)
            .where(
                RefreshToken.token_hash == token_hash,
                RefreshToken.used_at.is_(None),
                RefreshToken.revoked_at.is_(None),
                RefreshToken.expires_at > func.now(),
            )
            .values(used_at=func.now())
            .returning(RefreshToken)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def revoke_family(self, family_id: uuid.UUID) -> None:
        await self._lock_family(family_id)
        await self._session.execute(
            update(RefreshToken)
            .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=func.now())
        )
        # Commits here because the caller raises 401 next, and get_db skips its commit
        # when a route raises — the revocation must outlive the error response.
        await self._session.commit()
