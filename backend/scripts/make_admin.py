import argparse
import asyncio
import getpass
import logging
import sys

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import SessionLocal
from app.core.log_config import configure_logging
from app.core.security import verify_password
from app.models import User
from app.repositories import UserRepository

logger = logging.getLogger("make_admin")


async def set_admin_flag(session: AsyncSession, email: str, value: bool) -> bool:
    return await UserRepository(session).set_admin(email, value)


async def verify_owner(session: AsyncSession, email: str, password: str) -> User | None:
    user = await UserRepository(session).get_user_by_email(email)
    if user is None:
        return None
    if not await asyncio.to_thread(verify_password, password, user.hashed_password):
        return None
    return user


def _print_account(user: User) -> None:
    print(f"id:          {user.id}")
    print(f"created_at:  {user.created_at}")
    print(f"last_active: {user.last_active_at}")
    print(f"company:     {user.company}")
    print(f"role:        {user.role}")


async def _grant(email: str) -> int:
    async with SessionLocal() as session:
        user = await UserRepository(session).get_user_by_email(email)
        if user is None:
            print(f"no user with email {email}", file=sys.stderr)
            return 1
        _print_account(user)
        password = await asyncio.to_thread(getpass.getpass, "password for this account: ")
        # Emails are unverified, so owning the row's email proves nothing; the password does.
        owner = await verify_owner(session, email, password)
        if owner is None:
            print("password does not match this account — not granting", file=sys.stderr)
            return 2
        owner.is_admin = True
        await session.commit()
        logger.info("admin granted user_id=%s", owner.id)
        print(f"granted admin for {email} (id {owner.id})")
        return 0


async def _revoke(email: str) -> int:
    async with SessionLocal() as session:
        user = await UserRepository(session).get_user_by_email(email)
        if user is None:
            print(f"no user with email {email}", file=sys.stderr)
            return 1
        user_id = user.id
        print(f"id:          {user_id}")
        await set_admin_flag(session, email, False)
        await session.commit()
        logger.info("admin revoked user_id=%s", user_id)
        print(f"revoked admin for {email} (id {user_id})")
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Grant or revoke admin access for an existing account.",
        epilog=(
            "Run from backend/ with DATABASE_URL set. Granting asks for that account's password. "
            "Exit codes: 0 updated, 1 no such user, 2 password mismatch."
        ),
    )
    parser.add_argument("email")
    parser.add_argument("--revoke", action="store_true", help="remove admin access instead")
    args = parser.parse_args()

    configure_logging("INFO")
    return asyncio.run(_revoke(args.email) if args.revoke else _grant(args.email))


if __name__ == "__main__":
    sys.exit(main())
