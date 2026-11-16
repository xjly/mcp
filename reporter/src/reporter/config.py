"""PostgreSQL connection pool for the reporter tools."""

import asyncio
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from urllib.parse import quote, urlsplit

import asyncpg
from dotenv import load_dotenv
from mcp.server.fastmcp.exceptions import ToolError

load_dotenv()

QUERY_TIMEOUT_SECONDS = 30
logger = logging.getLogger(__name__)
_pool: asyncpg.Pool | None = None
_pool_lock = asyncio.Lock()


def _connection_parameters() -> dict[str, str | int]:
    url = os.getenv("DATABASE_URL", "")
    if not url:
        return {
            "host": os.getenv("POSTGRES_HOST", "localhost"),
            "port": int(os.getenv("POSTGRES_PORT", "5432")),
            "database": os.getenv("POSTGRES_DB", ""),
            "user": os.getenv("POSTGRES_USER", ""),
            "password": os.getenv("POSTGRES_PASSWORD", ""),
        }

    if url.startswith("postgresql+asyncpg://"):
        url = _legacy_dsn(url.removeprefix("postgresql+asyncpg://"))
    return {"dsn": url}


def _legacy_dsn(remainder: str) -> str:
    dsn = f"postgresql://{remainder}"
    user_info, separator, address = remainder.partition("@")
    username, colon, password = user_info.partition(":")
    if (
        not separator
        or not colon
        or any(c in username for c in "/?#")
        or not any(c in password for c in "/?#")
    ):
        return dsn

    # An unescaped password can resemble an invalid host:port. Preserve an
    # already valid authority when '@' is part of a normal connection option.
    try:
        parsed = urlsplit(dsn)
        _ = parsed.port
    except ValueError:
        pass
    else:
        if "@" in parsed.query:
            return dsn
    return f"postgresql://{quote(user_info, safe=':%')}@{address}"


async def get_pool() -> asyncpg.Pool:
    """Initialize one pool lazily, including when tools start concurrently."""
    global _pool
    async with _pool_lock:
        if _pool is None:
            _pool = await asyncpg.create_pool(
                **_connection_parameters(),
                min_size=0,
                max_size=10,
                timeout=QUERY_TIMEOUT_SECONDS,
                command_timeout=QUERY_TIMEOUT_SECONDS,
                server_settings={
                    "default_transaction_read_only": "on",
                    "statement_timeout": str(QUERY_TIMEOUT_SECONDS * 1000),
                    "TimeZone": "Asia/Shanghai",
                },
            )
        return _pool


async def close_pool() -> None:
    global _pool
    async with _pool_lock:
        if _pool is not None:
            pool, _pool = _pool, None
            try:
                await asyncio.wait_for(pool.close(), timeout=QUERY_TIMEOUT_SECONDS)
            except TimeoutError:
                pool.terminate()


@asynccontextmanager
async def get_db_connection() -> AsyncIterator[asyncpg.Connection]:
    """Bound the complete acquisition and query, including the wait for a pool slot."""
    try:
        async with asyncio.timeout(QUERY_TIMEOUT_SECONDS):
            pool = await get_pool()
            async with pool.acquire(timeout=QUERY_TIMEOUT_SECONDS) as conn:
                yield conn
    except (TimeoutError, asyncpg.QueryCanceledError):
        raise ToolError("报表查询达到 30 秒超时，请缩小查询范围后重试。") from None
    except (asyncpg.PostgresError, asyncpg.InterfaceError, OSError, ValueError) as exc:
        logger.warning("报表数据源错误：%s", type(exc).__name__)
        raise ToolError(
            "无法读取报表数据，请检查数据库连接、数据表和读取权限。"
        ) from None
