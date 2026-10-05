import argparse
import asyncio
import enum
import getpass
import logging
import sys
import uuid
from collections.abc import Awaitable
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import SessionLocal
from app.core.log_config import configure_logging
from app.core.security import hash_password, verify_password
from app.models import User
from app.repositories import UserRepository
from app.repositories.user_repo import EmailAlreadyExistsError
from app.schemas.auth import _within_bcrypt_limit, normalize_email

logger = logging.getLogger("make_admin")

ADMIN_PASSWORD_MIN_LENGTH = 16


class Result(enum.Enum):
    CREATED = "created"
    GRANTED = "granted"
    REVOKED = "revoked"
    NO_SUCH_USER = "no_such_user"
    WRONG_PASSWORD = "wrong_password"
    TOO_SHORT = "too_short"
    TOO_LONG = "too_long"
    MISMATCH = "mismatch"
    EMAIL_EXISTS = "email_exists"
    CHANGED = "changed"


EXIT_CODES = {
    Result.CREATED: 0,
    Result.GRANTED: 0,
    Result.REVOKED: 0,
    Result.NO_SUCH_USER: 1,
    Result.WRONG_PASSWORD: 2,
    Result.TOO_SHORT: 2,
    Result.TOO_LONG: 2,
    Result.MISMATCH: 2,
    Result.EMAIL_EXISTS: 3,
    Result.CHANGED: 5,
}
EXIT_INVALID_EMAIL = 2
EXIT_UNEXPECTED = 4


@dataclass(frozen=True)
class Outcome:
    result: Result
    user_id: uuid.UUID | None = None


def check_admin_password(password: str) -> Result | None:
    try:
        _within_bcrypt_limit(password)
    except ValueError:
        return Result.TOO_LONG
    if len(password) < ADMIN_PASSWORD_MIN_LENGTH:
        return Result.TOO_SHORT
    return None


async def create_admin(session: AsyncSession, email: str, password: str, confirm: str) -> Outcome:
    repo = UserRepository(session)
    if await repo.get_user_by_email(email) is not None:
        return Outcome(Result.EMAIL_EXISTS)
    if password != confirm:
        return Outcome(Result.MISMATCH)
    if (rejected := check_admin_password(password)) is not None:
        return Outcome(rejected)

    hashed = await asyncio.to_thread(hash_password, password)
    try:
        user = await repo.create_user(email, hashed, is_admin=True)
    except EmailAlreadyExistsError:
        return Outcome(Result.EMAIL_EXISTS)
    return Outcome(Result.CREATED, user.id)


async def grant_admin(
    session: AsyncSession, user_id: uuid.UUID, password: str, *, was_admin: bool
) -> Outcome:
    # By id, not email: a row deleted and re-registered under the same email while the
    # operator was typing is a different account and must not be promoted.
    user = await UserRepository(session).get_user_by_id(user_id)
    if user is None:
        return Outcome(Result.NO_SUCH_USER)
    if user.is_admin != was_admin:
        return Outcome(Result.CHANGED, user.id)
    if (rejected := check_admin_password(password)) is Result.TOO_LONG:
        return Outcome(rejected, user.id)
    # Emails are unverified, so owning the row's email proves nothing; the password does.
    if not await asyncio.to_thread(verify_password, password, user.hashed_password):
        return Outcome(Result.WRONG_PASSWORD, user.id)
    if rejected is not None:
        return Outcome(rejected, user.id)
    user.is_admin = True
    await session.flush()
    return Outcome(Result.GRANTED, user.id)


async def revoke_admin(session: AsyncSession, email: str) -> Outcome:
    repo = UserRepository(session)
    user = await repo.get_user_by_email(email)
    if user is None:
        return Outcome(Result.NO_SUCH_USER)
    await repo.set_admin(email, False)
    return Outcome(Result.REVOKED, user.id)


def _print_account(user: User) -> None:
    print(f"id:          {user.id}")
    print(f"created_at:  {user.created_at}")
    print(f"last_active: {user.last_active_at}")
    print(f"company:     {user.company}")
    print(f"role:        {user.role}")


def _prompt(label: str) -> Awaitable[str]:
    return asyncio.to_thread(getpass.getpass, label)


async def _email_taken(email: str) -> bool:
    async with SessionLocal() as session:
        return await UserRepository(session).get_user_by_email(email) is not None


async def _run_create(email: str) -> Outcome:
    if await _email_taken(email):
        return Outcome(Result.EMAIL_EXISTS)
    password = await _prompt("password for the new admin: ")
    confirm = await _prompt("confirm password: ")
    async with SessionLocal() as session:
        outcome = await create_admin(session, email, password, confirm)
        if outcome.result is Result.CREATED:
            await session.commit()
        return outcome


async def _run_grant(email: str) -> Outcome:
    async with SessionLocal() as session:
        user = await UserRepository(session).get_user_by_email(email)
        if user is None:
            return Outcome(Result.NO_SUCH_USER)
        _print_account(user)
        user_id, was_admin = user.id, user.is_admin
    # The read session is closed so no transaction stays open while the operator types.
    password = await _prompt("password for this account: ")
    async with SessionLocal() as session:
        outcome = await grant_admin(session, user_id, password, was_admin=was_admin)
        if outcome.result is Result.GRANTED:
            await session.commit()
        return outcome


async def _run_revoke(email: str) -> Outcome:
    async with SessionLocal() as session:
        outcome = await revoke_admin(session, email)
        if outcome.result is Result.REVOKED:
            await session.commit()
        return outcome


def _report(outcome: Outcome, email: str, grant: bool) -> None:
    messages = {
        Result.CREATED: f"created admin {email} (id {outcome.user_id})",
        Result.GRANTED: f"granted admin for {email} (id {outcome.user_id})",
        Result.REVOKED: f"revoked admin for {email} (id {outcome.user_id})",
    }
    errors = {
        Result.NO_SUCH_USER: f"no user with email {email}",
        Result.WRONG_PASSWORD: "password does not match this account — not granting",
        Result.TOO_SHORT: (
            "admin passwords must be at least 16 characters; create a dedicated admin with --create"
            if grant
            else "admin passwords must be at least 16 characters"
        ),
        Result.TOO_LONG: "password must not exceed 72 bytes when UTF-8 encoded",
        Result.MISMATCH: "passwords do not match",
        Result.EMAIL_EXISTS: (
            "an account with this email already exists — refusing to create an admin over it"
        ),
        Result.CHANGED: "the account changed while the password was being typed — nothing done",
    }
    if outcome.result in messages:
        logger.info("admin %s user_id=%s", outcome.result.value, outcome.user_id)
        print(messages[outcome.result])
    else:
        print(errors[outcome.result], file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create a dedicated admin account, or grant/revoke admin on an existing one.",
        epilog=(
            "Run from backend/ with DATABASE_URL set. --create is the normal way to make an admin. "
            "Granting asks for that account's password, which must be at least 16 characters. "
            "Exit codes: 0 done, 1 no such user, 2 password or email rejected, "
            "3 email already exists, 4 unexpected error, 5 account changed during the prompt."
        ),
    )
    parser.add_argument("email")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--create", action="store_true", help="create a new admin account")
    action.add_argument("--revoke", action="store_true", help="remove admin access instead")
    args = parser.parse_args()

    try:
        email = normalize_email(args.email)
    except ValueError as exc:
        print(f"not a valid email address: {exc}", file=sys.stderr)
        return EXIT_INVALID_EMAIL

    configure_logging("INFO")
    if args.create:
        run = _run_create(email)
    elif args.revoke:
        run = _run_revoke(email)
    else:
        run = _run_grant(email)
    try:
        outcome = asyncio.run(run)
        _report(outcome, email, grant=not (args.create or args.revoke))
    except Exception as exc:
        # The message can carry bound values or account data; the type is enough to debug.
        print(f"unexpected error: {type(exc).__name__}", file=sys.stderr)
        return EXIT_UNEXPECTED
    return EXIT_CODES[outcome.result]


if __name__ == "__main__":
    sys.exit(main())
