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
from app.schemas.auth import normalize_email

logger = logging.getLogger("delete_account")


class Result(enum.Enum):
    DELETED = "deleted"
    NOT_FOUND = "not_found"
    MISMATCH = "mismatch"
    ADMIN_REFUSED = "admin_refused"
    CHANGED = "changed"


EXIT_CODES = {
    Result.DELETED: 0,
    Result.NOT_FOUND: 1,
    Result.MISMATCH: 2,
    Result.ADMIN_REFUSED: 3,
    Result.CHANGED: 5,
}
EXIT_INVALID_EMAIL = 2
EXIT_UNEXPECTED = 4


@dataclass(frozen=True)
class Outcome:
    result: Result
    user_id: uuid.UUID | None = None


def confirmation_matches(email_on_record: str, typed: str) -> bool:
    # lower() on both sides mirrors the CITEXT comparison the lookup used.
    return typed.strip().lower() == email_on_record.lower()


async def erase_account(
    session: AsyncSession, user_id: uuid.UUID, *, was_admin: bool, allow_admin: bool = False
) -> Outcome:
    repo = UserRepository(session)
    user = await repo.get_user_by_id(user_id)
    if user is None:
        return Outcome(Result.NOT_FOUND)
    if user.is_admin != was_admin:
        return Outcome(Result.CHANGED, user_id)
    if user.is_admin and not allow_admin:
        return Outcome(Result.ADMIN_REFUSED, user_id)
    await repo.delete_by_id(user_id)
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
        user_id, was_admin, email_on_record = user.id, user.is_admin, user.email
    # The read session is closed so no transaction stays open while the operator types.
    confirm = await asyncio.to_thread(input, "type the email again to confirm: ")
    if not confirmation_matches(email_on_record, confirm):
        return Outcome(Result.MISMATCH, user_id)
    async with SessionLocal() as session:
        outcome = await erase_account(
            session, user_id, was_admin=was_admin, allow_admin=allow_admin
        )
        if outcome.result is Result.DELETED:
            await session.commit()
        return outcome


def _report(outcome: Outcome, email: str) -> None:
    if outcome.result is Result.DELETED:
        logger.info("account deleted user_id=%s", outcome.user_id)
        print(f"deleted {email} (id {outcome.user_id})")
    elif outcome.result is Result.NOT_FOUND:
        print(f"no user with email {email}", file=sys.stderr)
    elif outcome.result is Result.MISMATCH:
        print("confirmation does not match — nothing deleted", file=sys.stderr)
    elif outcome.result is Result.CHANGED:
        print("the account changed while you were confirming — nothing deleted", file=sys.stderr)
    else:
        print("this is an admin account; pass --allow-admin to delete it", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Delete an account and its sessions, for an erasure request.",
        epilog=(
            "Run from backend/ with DATABASE_URL set. Asks for the email again before deleting. "
            "Exit codes: 0 deleted, 1 no such user, 2 confirmation mismatch or invalid email, "
            "3 admin account (pass --allow-admin), 4 unexpected error, "
            "5 account changed during the prompt."
        ),
    )
    parser.add_argument("email")
    parser.add_argument("--allow-admin", action="store_true", help="allow deleting an admin")
    args = parser.parse_args()

    try:
        email = normalize_email(args.email)
    except ValueError as exc:
        print(f"not a valid email address: {exc}", file=sys.stderr)
        return EXIT_INVALID_EMAIL

    configure_logging("INFO")
    try:
        outcome = asyncio.run(_run(email, args.allow_admin))
        _report(outcome, email)
    except Exception as exc:
        # The message can carry bound values or account data; the type is enough to debug.
        print(f"unexpected error: {type(exc).__name__}", file=sys.stderr)
        return EXIT_UNEXPECTED
    return EXIT_CODES[outcome.result]


if __name__ == "__main__":
    sys.exit(main())
