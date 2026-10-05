import argparse
import asyncio
import sys

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import SessionLocal
from app.repositories import UserRepository


async def set_admin_flag(session: AsyncSession, email: str, value: bool) -> bool:
    return await UserRepository(session).set_admin(email, value)


async def _run(email: str, value: bool) -> bool:
    async with SessionLocal() as session:
        found = await set_admin_flag(session, email, value)
        await session.commit()
    return found


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Grant or revoke admin access for an existing account.",
        epilog="Run from backend/ with DATABASE_URL set. Exit codes: 0 updated, 1 no such user.",
    )
    parser.add_argument("email")
    parser.add_argument("--revoke", action="store_true", help="remove admin access instead")
    args = parser.parse_args()

    found = asyncio.run(_run(args.email, not args.revoke))
    if not found:
        print(f"no user with email {args.email}", file=sys.stderr)
        return 1
    print(f"{'revoked' if args.revoke else 'granted'} admin for {args.email}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
