import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

import asyncpg

from core.config import get_settings

logger = logging.getLogger(__name__)

_pool: asyncpg.Pool | None = None


async def init_pool(min_size: int = 1, max_size: int = 5) -> asyncpg.Pool:
    global _pool
    settings = get_settings()
    logger.info("Initializing asyncpg connection pool...")
    _pool = await asyncpg.create_pool(
        **settings.db_connect_args,
        min_size=min_size,
        max_size=max_size,
    )
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        logger.info("Closing asyncpg connection pool...")
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Database pool is not initialized. Call init_pool() first.")
    return _pool


@asynccontextmanager
async def acquire_connection() -> AsyncIterator[asyncpg.Connection]:
    async with get_pool().acquire() as conn:
        yield conn


async def fetch_all(query: str) -> list[dict]:
    async with acquire_connection() as conn:
        rows = await conn.fetch(query)
        return [dict(row) for row in rows]
