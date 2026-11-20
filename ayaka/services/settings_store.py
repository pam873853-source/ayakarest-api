"""System settings (maintenance mode, registration, defaults) with a short cache."""
from __future__ import annotations

import datetime as dt
import time
from typing import Any

from psycopg.types.json import Jsonb

from .. import db

_cache: dict[str, tuple[float, Any]] = {}
_TTL = 5.0

DEFAULTS: dict[str, Any] = {
    "maintenance": {"enabled": False, "message": "AYAKA API sedang dalam pemeliharaan terjadwal.",
                    "start_at": None, "end_at": None},
    "registration": {"open": True},
    "defaults": {"rate_limit_per_minute": 60, "monthly_quota": 10000},
}


def get(key: str) -> Any:
    hit = _cache.get(key)
    if hit and hit[0] > time.monotonic():
        return hit[1]
    row = db.fetchone("SELECT value FROM system_settings WHERE key = %s", (key,))
    value = row["value"] if row else DEFAULTS.get(key)
    _cache[key] = (time.monotonic() + _TTL, value)
    return value


def set_value(key: str, value: Any, user_id: str | None) -> None:
    db.execute(
        """INSERT INTO system_settings (key, value, updated_by) VALUES (%s, %s, %s)
           ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_by = EXCLUDED.updated_by""",
        (key, Jsonb(value), user_id),
    )
    _cache.pop(key, None)


def clear_cache() -> None:
    _cache.clear()


def _parse(ts: str | None) -> dt.datetime | None:
    if not ts:
        return None
    try:
        d = dt.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)
    except ValueError:
        return None


def maintenance_state() -> dict:
    m = dict(get("maintenance") or DEFAULTS["maintenance"])
    now = dt.datetime.now(dt.timezone.utc)
    start, end = _parse(m.get("start_at")), _parse(m.get("end_at"))
    active = bool(m.get("enabled")) and (start is None or now >= start) and (end is None or now < end)
    scheduled = bool(m.get("enabled")) and start is not None and now < start
    m["active"] = active
    m["scheduled"] = scheduled
    return m
