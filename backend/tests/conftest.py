import asyncio
import os
import subprocess
from collections.abc import AsyncGenerator, Generator
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("SECRET_KEY", "test-secret-not-real-" + "x" * 32)


def _base_database_url() -> str:
    explicit = os.environ.get("TEST_DATABASE_URL")
    if explicit:
        return explicit
    env_file = Path(__file__).resolve().parents[2] / ".env"
    for line in env_file.read_text().splitlines():
        if line.startswith("DATABASE_URL="):
            url = urlsplit(line.split("=", 1)[1].strip())
            return urlunsplit(url._replace(path=url.path + "_test"))
    raise RuntimeError("set TEST_DATABASE_URL or provide DATABASE_URL in .env")


def _test_database_url() -> str:
    # Per-process name: setup DROPs the database WITH (FORCE), which would terminate
    # a concurrent run's connections if every process shared one name.
    url = urlsplit(_base_database_url())
    worker = os.environ.get("PYTEST_XDIST_WORKER") or str(os.getpid())
    return urlunsplit(url._replace(path=f"{url.path}_{worker}"))


TEST_DATABASE_URL = _test_database_url()
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.db import get_db
from app.main import app

DB_NAME = urlsplit(TEST_DATABASE_URL.replace("+asyncpg", "")).path.lstrip("/")


async def _on_postgres(*statements: str) -> None:
    import asyncpg

    url = urlsplit(TEST_DATABASE_URL.replace("+asyncpg", ""))
    conn = await asyncpg.connect(urlunsplit(url._replace(path="/postgres")))
    try:
        for statement in statements:
            await conn.execute(statement)
    finally:
        await conn.close()


@pytest.fixture(scope="session", autouse=True)
def _test_db() -> Generator[None]:
    asyncio.run(
        _on_postgres(
            f'DROP DATABASE IF EXISTS "{DB_NAME}" WITH (FORCE)',
            f'CREATE DATABASE "{DB_NAME}"',
        )
    )
    subprocess.run(
        ["alembic", "upgrade", "head"],
        cwd=Path(__file__).resolve().parents[1],
        check=True,
        env=os.environ,
    )

    yield

    asyncio.run(engine.dispose())
    asyncio.run(_on_postgres(f'DROP DATABASE IF EXISTS "{DB_NAME}" WITH (FORCE)'))


engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession]:
    async with engine.connect() as conn:
        outer = await conn.begin()
        session = AsyncSession(
            bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False
        )
        yield session
        await session.close()
        await outer.rollback()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[httpx.AsyncClient]:
    async def override_get_db() -> AsyncGenerator[AsyncSession]:
        yield db_session
        await db_session.commit()

    app.dependency_overrides[get_db] = override_get_db
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="https://test") as c:
        yield c
    app.dependency_overrides.clear()
