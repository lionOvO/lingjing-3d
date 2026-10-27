"""Async SQLAlchemy engine and request-scoped session helpers."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .config import settings
from .models import Base

engine = create_async_engine(
    settings.database_url,
    # aiomysql's async connection adapter in the current image exposes
    # ``ping()`` without SQLAlchemy's reconnect argument.  SQLAlchemy 2.0
    # therefore raises before every request when pool_pre_ping is enabled.
    # Connection recycling still prevents stale long-lived connections while
    # avoiding that incompatible ping call.
    pool_pre_ping=False,
    pool_recycle=1800,
    echo=settings.sql_echo,
)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide one transaction-aware session for each HTTP request."""
    async with SessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def create_schema() -> None:
    """Create the schema for local Compose deployments when it is absent."""
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


async def close_database() -> None:
    await engine.dispose()
