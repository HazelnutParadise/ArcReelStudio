"""Database package — ORM models, engine, and session factory."""

import contextlib
import logging

from lib.db.base import Base
from lib.db.engine import (
    async_engine,
    async_session_factory,
    get_async_session,
    get_database_url,
    is_sqlite_backend,
    safe_session_factory,
)

_log = logging.getLogger(__name__)


async def init_db() -> None:
    """Run Alembic migrations to initialise / upgrade the database schema.

    使用 Config() 空构造 + set_main_option 编程式调用 alembic，
    而非 Config("alembic.ini")，避免 env.py 的 fileConfig() 覆盖应用日志配置。
    """
    import asyncio
    from pathlib import Path

    from alembic.config import Config

    from alembic import command

    def _run_alembic():
        project_root = Path(__file__).parent.parent.parent
        cfg = Config()
        cfg.set_main_option("script_location", str(project_root / "alembic"))
        command.upgrade(cfg, "head")

    await asyncio.get_event_loop().run_in_executor(None, _run_alembic)
    _log.info("Database schema is up to date")


async def close_db() -> None:
    """Dispose engine connections on shutdown.

    aiosqlite connections may already be dead when SSE tasks were cancelled,
    so we tolerate errors during pool cleanup.
    """
    with contextlib.suppress(Exception):
        await async_engine.dispose()


__all__ = [
    "Base",
    "async_engine",
    "async_session_factory",
    "close_db",
    "get_async_session",
    "get_database_url",
    "init_db",
    "is_sqlite_backend",
    "safe_session_factory",
]
