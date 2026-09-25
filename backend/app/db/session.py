"""Async engine and session dependency."""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.exc import ArgumentError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings

_settings = get_settings()


def _engine_for(url: str):
    """Build the engine, saying plainly what is wrong with a bad DATABASE_URL.

    SQLAlchemy's own complaint is "Could not parse SQLAlchemy URL from given URL
    string", which does not distinguish an unset variable from a mistyped one, and
    arrives buried in an import-time traceback.
    """
    if not url.strip():
        raise RuntimeError(
            "DATABASE_URL is empty. Set it in the host's environment; on Render that "
            "means the Environment tab, and the value is not applied until saved."
        )
    if url.startswith("postgresql://") or url.startswith("postgres://"):
        raise RuntimeError(
            "DATABASE_URL names a sync driver. Change the scheme to "
            "'postgresql+asyncpg://' and drop any '?sslmode=' parameters, which "
            "asyncpg rejects."
        )
    try:
        return create_async_engine(url, echo=False, future=True)
    except ArgumentError as exc:
        raise RuntimeError(
            f"DATABASE_URL could not be parsed ({exc}). Expected "
            "postgresql+asyncpg://user:password@host/database with no quotes, "
            "spaces or line breaks."
        ) from exc


engine = _engine_for(_settings.database_url)
SessionFactory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionFactory() as session:
        yield session
