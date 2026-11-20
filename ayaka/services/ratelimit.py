"""Serverless-safe fixed-window rate limiter backed by Postgres.

In-memory counters do not work on Vercel (many short-lived instances), so every
counter lives in `rate_limit_counters` and is incremented atomically with UPSERT.
"""
from __future__ import annotations

import random

from .. import db
from ..responses import ApiError


def hit(bucket: str, limit: int, window_seconds: int) -> tuple[bool, int, int]:
    """Increment bucket. Returns (allowed, remaining, retry_after_seconds)."""
    row = db.fetchone(
        """
        WITH w AS (
          SELECT to_timestamp(floor(extract(epoch FROM now()) / %(w)s) * %(w)s) AS ws
        )
        INSERT INTO rate_limit_counters (bucket, window_start, count, expires_at)
        SELECT %(b)s, ws, 1, ws + make_interval(secs => %(w)s) FROM w
        ON CONFLICT (bucket, window_start)
        DO UPDATE SET count = rate_limit_counters.count + 1
        RETURNING count, GREATEST(1, ceil(extract(epoch FROM (expires_at - now()))))::int AS retry
        """,
        {"b": bucket[:160], "w": window_seconds},
    )
    if random.random() < 0.02:
        db.execute("DELETE FROM rate_limit_counters WHERE expires_at < now() - interval '1 hour'")
    count = row["count"]
    return count <= limit, max(0, limit - count), row["retry"]


def peek(bucket: str, window_seconds: int) -> int:
    v = db.scalar(
        """SELECT count FROM rate_limit_counters
           WHERE bucket = %(b)s
             AND window_start = to_timestamp(floor(extract(epoch FROM now()) / %(w)s) * %(w)s)""",
        {"b": bucket[:160], "w": window_seconds},
    )
    return int(v or 0)


def reset(bucket: str) -> None:
    db.execute("DELETE FROM rate_limit_counters WHERE bucket = %s", (bucket[:160],))


def enforce(bucket: str, limit: int, window_seconds: int, code: str = "RATE_LIMITED",
            message: str = "Terlalu banyak request. Coba lagi nanti.") -> int:
    allowed, remaining, retry = hit(bucket, limit, window_seconds)
    if not allowed:
        raise ApiError(429, code, message, details={"retry_after": retry},
                       headers={"Retry-After": str(retry), "X-RateLimit-Limit": str(limit),
                                "X-RateLimit-Remaining": "0"})
    return remaining
