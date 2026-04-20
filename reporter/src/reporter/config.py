"""Database configuration - PostgreSQL async connection settings"""

import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import AsyncGenerator

import asyncpg
from dotenv import load_dotenv

load_dotenv()


@dataclass
class DatabaseConfig:
    host: str
    port: int
    database: str
    user: str
    password: str


def _parse_connection_string(url: str) -> DatabaseConfig:
    """Parse postgresql+asyncpg://... URL into components"""
    # URL format: postgresql+asyncpg://user:password@host:port/db
    url = url.replace("postgresql+asyncpg://", "")
    if "@" not in url:
        raise ValueError("Invalid connection string: missing '@'")

    auth, rest = url.split("@", 1)
    if ":" in auth:
        user, password = auth.split(":", 1)
    else:
        user = auth
        password = ""

    if "/" not in rest:
        raise ValueError("Invalid connection string: missing database")
    host_port, database = rest.rsplit("/", 1)

    if ":" in host_port:
        host, port = host_port.split(":", 1)
        port = int(port)
    else:
        host = host_port
        port = 5432

    return DatabaseConfig(
        host=host,
        port=port,
        database=database,
        user=user,
        password=password,
    )


def get_db_config() -> DatabaseConfig:
    url = os.getenv("DATABASE_URL", "")
    if url:
        return _parse_connection_string(url)

    return DatabaseConfig(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        database=os.getenv("POSTGRES_DB", ""),
        user=os.getenv("POSTGRES_USER", ""),
        password=os.getenv("POSTGRES_PASSWORD", ""),
    )


_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    """Get or create the connection pool"""
    global _pool
    if _pool is None:
        config = get_db_config()
        _pool = await asyncpg.create_pool(
            host=config.host,
            port=config.port,
            database=config.database,
            user=config.user,
            password=config.password,
            min_size=1,
            max_size=10,
        )
    return _pool


async def close_pool():
    """Close the connection pool"""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


@asynccontextmanager
async def get_db_connection() -> AsyncGenerator[asyncpg.Connection, None]:
    """Get a connection from the pool"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        yield conn