"""Audit logging and in-app notifications."""
from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from .. import db


def audit(action: str, *, actor_type: str, actor_id: str | None = None, user_id: str | None = None,
          target_type: str | None = None, target_id: str | None = None,
          metadata: dict[str, Any] | None = None, ip_masked: str | None = None, conn=None) -> None:
    db.execute(
        """INSERT INTO audit_logs (actor_type, actor_id, user_id, action, target_type, target_id, metadata, ip_masked)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
        (actor_type, str(actor_id) if actor_id else None, user_id, action, target_type,
         str(target_id) if target_id else None, Jsonb(metadata or {}), ip_masked),
        conn=conn,
    )


def notify(user_id: str, title: str, body: str = "", kind: str = "info", conn=None) -> None:
    db.execute(
        "INSERT INTO notifications (user_id, kind, title, body) VALUES (%s, %s, %s, %s)",
        (user_id, kind, title[:120], body[:500]), conn=conn,
    )
