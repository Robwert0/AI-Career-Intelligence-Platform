import argparse
import asyncio
import enum
import logging
import sys
import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import SessionLocal
from app.core.log_config import configure_logging
from app.repositories import UserRepository

logger = logging.getLogger("delete_account")


class Result(enum.Enum):
    DELETED = "deleted"
    NOT_FOUND = "not_found"
    MISMATCH = "mismatch"
    ADMIN_REFUSED = "admin_refused"


EXIT_CODES = {Result.DELETED: 0, Result.NOT_FOUND: 1, Result.MISMATCH: 2, Result.ADMIN_REFUSED: 3}
EXIT_UNEXPECTED = 4


@dataclass(frozen=True)
class Outcome:
    result: Result
    user_id: uuid.UUID | None = None


async def erase_account(
    session: AsyncSession, email: str, confirm: str, *, allow_admin: bool = False
) -> Outcome:
    repo = UserRepository(session)
    user = await repo.get_user_by_email(email)
    if user is None:
        return Outcome(Result.NOT_FOUND)
    if user.is_admin and not allow_admin:
        return Outcome(Result.ADMIN_REFUSED, user.id)
    # Emails are CITEXT, so the confirmation is compared the same way the lookup was.
    if confirm.strip().casefold() != user.email.casefold():
        return Outcome(Result.MISMATCH, user.id)
    user_id = user.id
    await repo.delete_by_email(email)
    return Outcome(Result.DELETED, user_id)


async def _run(email: str, allow_admin: bool) -> Outcome:
    async with SessionLocal() as session:
        user = await UserRepository(session).get_user_by_email(email)
        if user is None:
            return Outcome(Result.NOT_FOUND)
        print(f"id:          {user.id}")
        print(f"created_at:  {user.created_at}")
        if user.is_admin and not allow_admin:
            return Outcome(Result.ADMIN_REFUSED, user.id)
        confirm = await asyncio.to_thread(input, "type the email again to confirm: ")
        outcome = await erase_account(session, email, confirm, allow_admin=allow_admin)
        if outcome.result is Result.DELETED:
            await session.commit()
        return outcome


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Delete an account and its sessions, for an erasure request.",
        epilog=(
            "Run from backend/ with DATABASE_URL set. Asks for the email again before deleting. "
            "Exit codes: 0 deleted, 1 no such user, 2 confirmation mismatch, "
            "3 admin account (pass --allow-admin), 4 unexpected error."
        ),
    )
    parser.add_argument("email")
    parser.add_argument("--allow-admin", action="store_true", help="allow deleting an admin")
    args = parser.parse_args()

    configure_logging("INFO")
    try:
        outcome = asyncio.run(_run(args.email, args.allow_admin))
    except Exception as exc:
        # The message can carry bound values or account data; the type is enough to debug.
        print(f"unexpected error: {type(exc).__name__}", file=sys.stderr)
        return EXIT_UNEXPECTED

    if outcome.result is Result.DELETED:
        logger.info("account deleted user_id=%s", outcome.user_id)
        print(f"deleted {args.email} (id {outcome.user_id})")
    elif outcome.result is Result.NOT_FOUND:
        print(f"no user with email {args.email}", file=sys.stderr)
    elif outcome.result is Result.MISMATCH:
        print("confirmation does not match — nothing deleted", file=sys.stderr)
    else:
        print("this is an admin account; pass --allow-admin to delete it", file=sys.stderr)
    return EXIT_CODES[outcome.result]


if __name__ == "__main__":
    sys.exit(main())
