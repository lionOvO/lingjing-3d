import os
import sys
import tempfile
from pathlib import Path

# Keep the SQLite test file in the workspace root, which is writable even when
# pytest is launched with ``backend`` as its working directory.
# The source checkout can be mounted read-only by CI or Codex.  Tests own a
# per-process database in the system temporary directory instead.
TEST_DB_PATH = Path(tempfile.gettempdir()) / f"moonlit_test_{os.getpid()}.db"
TEST_DATABASE_URL = f"sqlite+aiosqlite:///{TEST_DB_PATH.as_posix()}"
os.environ.setdefault("DATABASE_URL", TEST_DATABASE_URL)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import get_db_session
from app.main import app
from app.models import Base

# Use a dedicated runtime database so a checked-in/read-only test artifact
# cannot make the async fixture fail before tests execute.
test_engine = create_async_engine(TEST_DATABASE_URL)
TestSession = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture(autouse=True)
async def reset_database():
    async with test_engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    yield


@pytest_asyncio.fixture
async def client():
    async def override_session():
        async with TestSession() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def db_session():
    async with TestSession() as session:
        yield session
