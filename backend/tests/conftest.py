import asyncio
import os
import subprocess
from collections.abc import AsyncGenerator
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("SECRET_KEY", "test-secret-not-real-" + "x" * 32)


def _test_database_url() -> str:
    explicit = os.environ.get("TEST_DATABASE_URL")
    if explicit:
        return explicit
    env_file = Path(__file__).resolve().parents[2] / ".env"
    for line in env_file.read_text().splitlines():
        if line.startswith("DATABASE_URL="):
            url = urlsplit(line.split("=", 1)[1].strip())
            return urlunsplit(url._replace(path=url.path + "_test"))
    raise RuntimeError("set TEST_DATABASE_URL or provide DATABASE_URL in .env")


TEST_DATABASE_URL = _test_database_url()
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.db import get_db
from app.main import app


async def _recreate_database() -> None:
    import asyncpg

    url = urlsplit(TEST_DATABASE_URL.replace("+asyncpg", ""))
    db_name = url.path.lstrip("/")
    conn = await asyncpg.connect(urlunsplit(url._replace(path="/postgres")))
    try:
        await conn.execute(f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE)')
        await conn.execute(f'CREATE DATABASE "{db_name}"')
    finally:
        await conn.close()


@pytest.fixture(scope="session", autouse=True)
def _test_db() -> None:
    asyncio.run(_recreate_database())
    subprocess.run(
        ["alembic", "upgrade", "head"],
        cwd=Path(__file__).resolve().parents[1],
        check=True,
        env=os.environ,
    )


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
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
