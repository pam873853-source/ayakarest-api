"""Neon PostgreSQL access layer (psycopg 3 + connection pool).

On Vercel each warm serverless instance keeps a tiny pool. Use Neon's *pooled*
connection string (host contains `-pooler`) so PgBouncer multiplexes connections.
All queries use server-side parameter binding (no string formatting) → SQL injection safe.
"""
from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Any, Iterator

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .config import get_settings

_pool: ConnectionPool | None = None
_lock = threading.Lock()


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        with _lock:
            if _pool is None:
                url = get_settings().database_url
                if not url:
                    raise RuntimeError("DATABASE_URL is not configured")
                _pool = ConnectionPool(
                    conninfo=url,
                    min_size=0,
                    max_size=4,
                    max_idle=60,
                    timeout=10,
                    open=True,
                    check=ConnectionPool.check_connection,
                    kwargs={"row_factory": dict_row, "autocommit": True,
                            "prepare_threshold": None, "connect_timeout": 10},
                )
    return _pool


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


@contextmanager
def connection() -> Iterator[psycopg.Connection]:
    with get_pool().connection() as conn:
        yield conn


@contextmanager
def transaction() -> Iterator[psycopg.Connection]:
    """Atomic block: commits on success, rolls back on any exception."""
    with get_pool().connection() as conn:
        with conn.transaction():
            yield conn


def fetchone(sql: str, params: Any = None, conn: psycopg.Connection | None = None) -> dict | None:
    if conn is not None:
        return conn.execute(sql, params).fetchone()
    with connection() as c:
        return c.execute(sql, params).fetchone()


def fetchall(sql: str, params: Any = None, conn: psycopg.Connection | None = None) -> list[dict]:
    if conn is not None:
        return conn.execute(sql, params).fetchall()
    with connection() as c:
        return c.execute(sql, params).fetchall()


def execute(sql: str, params: Any = None, conn: psycopg.Connection | None = None) -> int:
    if conn is not None:
        return conn.execute(sql, params).rowcount
    with connection() as c:
        return c.execute(sql, params).rowcount


def scalar(sql: str, params: Any = None, conn: psycopg.Connection | None = None) -> Any:
    row = fetchone(sql, params, conn)
    if not row:
        return None
    return next(iter(row.values()))
