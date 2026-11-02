"""Async database setup and migrations."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

from alembic import command
from alembic.config import Config as AlembicConfig
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from mergechat.config import Settings
from mergechat.storage.models import Base


def create_engine(settings: Settings) -> AsyncEngine:
    connect_args: dict[str, object] = {}
    if settings.async_database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    return create_async_engine(
        settings.async_database_url,
        echo=False,
        future=True,
        connect_args=connect_args,
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def init_db(engine: AsyncEngine) -> None:
    """Create tables directly; used by isolated tests only."""
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


def _alembic_config(settings: Settings) -> AlembicConfig:
    ini_path = Path(__file__).resolve().parents[3] / "alembic.ini"
    config = AlembicConfig(str(ini_path))
    config.attributes["settings"] = settings
    return config


def run_migrations(settings: Settings) -> None:
    """Apply Alembic migrations synchronously in a worker thread."""
    command.upgrade(_alembic_config(settings), "head")


async def ensure_schema(settings: Settings) -> None:
    await asyncio.to_thread(run_migrations, settings)


async def session_scope(
    factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    async with factory() as session:
        yield session
