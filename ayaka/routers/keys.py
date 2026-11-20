"""API Key Manager. Raw secrets are returned exactly once (on create/regenerate)."""
from __future__ import annotations

import datetime as dt
import uuid

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from .. import db
from ..config import PERMISSIONS
from ..deps import Principal, require, require_session
from ..responses import ApiError, ok
from ..security import generate_api_key, hash_api_key
from ..services import settings_store, webhooks
from ..services.activity import audit, notify
from ..utils import masked_ip

router = APIRouter(prefix="/api/keys", tags=["api-keys"])
MAX_ACTIVE_KEYS = 25
KEY_COLUMNS = """id, owner_id, name, description, key_prefix, key_last4, permissions, rate_limit_per_minute,
                 status, expires_at, last_used_at, usage_count, revoked_at, revoked_reason, rotated_from,
                 created_at, updated_at"""


class GenerateIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=300)
    permissions: list[str] = Field(default_factory=lambda: ["profile:read"], max_length=len(PERMISSIONS))
    expires_in_days: int | None = Field(default=None, ge=1, le=3650)
    rate_limit_per_minute: int | None = Field(default=None, ge=1, le=1000)


class UpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=300)
    permissions: list[str] | None = None
    rate_limit_per_minute: int | None = Field(default=None, ge=1, le=1000)


class RevokeIn(BaseModel):
    reason: str | None = Field(default=None, max_length=120)


def _uuid(value: str) -> str:
    try:
        return str(uuid.UUID(value))
    except ValueError:
        raise ApiError(404, "KEY_NOT_FOUND", "API Key tidak ditemukan")


def _check_perms(perms: list[str]) -> list[str]:
    bad = [p for p in perms if p not in PERMISSIONS]
    if bad:
        raise ApiError(422, "INVALID_PERMISSION", f"Permission tidak dikenal: {', '.join(bad)}",
                       details={"allowed": list(PERMISSIONS)})
    if not perms:
        raise ApiError(422, "INVALID_PERMISSION", "Pilih minimal satu permission")
    return sorted(set(perms))


def serialize(k: dict) -> dict:
    now = dt.datetime.now(dt.timezone.utc)
    status = k["status"]
    if status == "active" and k["expires_at"] is not None and k["expires_at"] <= now:
        status = "expired"
    return {
        "id": k["id"], "name": k["name"], "description": k["description"],
        "masked_key": f"{k['key_prefix']}{'•' * 8}{k['key_last4']}",
        "permissions": k["permissions"], "rate_limit_per_minute": k["rate_limit_per_minute"],
        "status": status, "expires_at": k["expires_at"], "last_used_at": k["last_used_at"],
        "usage_count": k["usage_count"], "revoked_at": k["revoked_at"], "revoked_reason": k["revoked_reason"],
        "rotated_from": k["rotated_from"], "created_at": k["created_at"], "updated_at": k["updated_at"],
    }


def _get_owned(key_id: str, owner_id: str, conn=None, lock: bool = False) -> dict:
    row = db.fetchone(f"SELECT {KEY_COLUMNS} FROM api_keys WHERE id = %s AND owner_id = %s"
                      + (" FOR UPDATE" if lock else ""), (_uuid(key_id), owner_id), conn)
    if not row:  # same response for "missing" and "belongs to someone else"
        raise ApiError(404, "KEY_NOT_FOUND", "API Key tidak ditemukan")
    return row


def _insert_key(conn, owner_id: str, name: str, description: str, perms: list[str],
                expires_at, rate: int, rotated_from=None) -> tuple[dict, str]:
    raw = generate_api_key()
    row = db.fetchone(
        f"""INSERT INTO api_keys (owner_id, name, description, key_prefix, key_last4, key_hash, permissions,
                                 rate_limit_per_minute, expires_at, rotated_from)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING {KEY_COLUMNS}""",
        (owner_id, name, description, raw[:15], raw[-4:], hash_api_key(raw), perms, rate, expires_at,
         rotated_from), conn)
    return row, raw


@router.get("")
def list_keys(request: Request, p: Principal = Depends(require("keys:read")), status: str | None = None):
    rows = db.fetchall(f"SELECT {KEY_COLUMNS} FROM api_keys WHERE owner_id = %s ORDER BY created_at DESC",
                       (p.user_id,))
    items = [serialize(r) for r in rows]
    counts = {s: sum(1 for i in items if i["status"] == s) for s in ("active", "revoked", "expired")}
    if status in {"active", "revoked", "expired"}:
        items = [i for i in items if i["status"] == status]
    return ok({"items": items, "total": len(items), "counts": counts,
               "available_permissions": PERMISSIONS})


@router.get("/permissions")
def permissions():
    return ok({"permissions": PERMISSIONS})


@router.get("/history")
def history(p: Principal = Depends(require_session)):
    rows = db.fetchall(
        """SELECT action, target_id, metadata, ip_masked, created_at FROM audit_logs
            WHERE user_id = %s AND action LIKE 'key.%%' ORDER BY created_at DESC LIMIT 100""", (p.user_id,))
    return ok({"items": rows})


@router.post("/generate")
def generate(body: GenerateIn, request: Request, p: Principal = Depends(require_session)):
    perms = _check_perms(body.permissions)
    default_rate = int((settings_store.get("defaults") or {}).get("rate_limit_per_minute", 60))
    rate = body.rate_limit_per_minute or default_rate
    expires_at = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=body.expires_in_days)
                  if body.expires_in_days else None)
    with db.transaction() as conn:
        active = db.scalar("""SELECT count(*) FROM api_keys WHERE owner_id = %s AND status = 'active'
                              AND (expires_at IS NULL OR expires_at > now())""", (p.user_id,), conn)
        if active >= MAX_ACTIVE_KEYS:
            raise ApiError(409, "KEY_LIMIT_REACHED", f"Maksimal {MAX_ACTIVE_KEYS} API Key aktif per akun")
        row, raw = _insert_key(conn, p.user_id, body.name.strip(), body.description.strip(), perms,
                               expires_at, rate)
        audit("key.created", actor_type="user", actor_id=p.user_id, user_id=p.user_id, target_type="api_key",
              target_id=str(row["id"]), metadata={"name": row["name"], "permissions": perms},
              ip_masked=masked_ip(request), conn=conn)
        notify(p.user_id, "API Key dibuat", f"API Key '{row['name']}' berhasil dibuat.", "success", conn=conn)
    webhooks.dispatch(p.user_id, "key.created", {"key_id": row["id"], "name": row["name"]})
    data = serialize(row)
    data["api_key"] = raw
    data["warning"] = ("Simpan API Key ini sekarang. Secret lengkap hanya ditampilkan sekali "
                       "dan tidak dapat dilihat kembali.")
    return ok(data, "API Key berhasil dibuat", 201)


@router.get("/{key_id}")
def detail(key_id: str, p: Principal = Depends(require("keys:read"))):
    row = _get_owned(key_id, p.user_id)
    stats = db.fetchone(
        """SELECT count(*) AS total, count(*) FILTER (WHERE status_code < 400) AS success,
                  count(*) FILTER (WHERE status_code >= 400) AS failed,
                  coalesce(round(avg(response_time_ms)), 0) AS avg_ms
             FROM api_request_logs WHERE api_key_id = %s""", (row["id"],))
    usage = db.fetchall(
        """SELECT d::date AS day, count(l.id) AS requests
             FROM generate_series(date_trunc('day', now()) - interval '13 days', date_trunc('day', now()), interval '1 day') d
        LEFT JOIN api_request_logs l ON l.api_key_id = %s AND l.created_at >= d AND l.created_at < d + interval '1 day'
         GROUP BY d ORDER BY d""", (row["id"],))
    data = serialize(row)
    data["stats"] = stats
    data["usage_by_day"] = usage
    return ok(data)


@router.patch("/{key_id}")
def update(key_id: str, body: UpdateIn, request: Request, p: Principal = Depends(require_session)):
    with db.transaction() as conn:
        row = _get_owned(key_id, p.user_id, conn, lock=True)
        if row["status"] == "revoked":
            raise ApiError(409, "KEY_REVOKED", "API Key yang sudah dicabut tidak dapat diubah")
        perms = _check_perms(body.permissions) if body.permissions is not None else row["permissions"]
        row = db.fetchone(
            f"""UPDATE api_keys SET name = %s, description = %s, permissions = %s, rate_limit_per_minute = %s
                 WHERE id = %s RETURNING {KEY_COLUMNS}""",
            ((body.name or row["name"]).strip(),
             (body.description if body.description is not None else row["description"]).strip(),
             perms, body.rate_limit_per_minute or row["rate_limit_per_minute"], row["id"]), conn)
        audit("key.updated", actor_type="user", actor_id=p.user_id, user_id=p.user_id, target_type="api_key",
              target_id=str(row["id"]), metadata=body.model_dump(exclude_none=True),
              ip_masked=masked_ip(request), conn=conn)
    return ok(serialize(row), "API Key diperbarui")


def revoke_key(key_id: str, owner_id: str, actor_type: str, actor_id: str, reason: str | None,
               ip: str | None) -> dict:
    with db.transaction() as conn:
        row = _get_owned(key_id, owner_id, conn, lock=True)
        if row["status"] == "revoked":
            raise ApiError(409, "KEY_ALREADY_REVOKED", "API Key sudah dicabut sebelumnya")
        row = db.fetchone(
            f"""UPDATE api_keys SET status = 'revoked', revoked_at = now(), revoked_reason = %s
                 WHERE id = %s RETURNING {KEY_COLUMNS}""", (reason or "revoked by owner", row["id"]), conn)
        audit("key.revoked", actor_type=actor_type, actor_id=actor_id, user_id=owner_id, target_type="api_key",
              target_id=str(row["id"]), metadata={"reason": reason}, ip_masked=ip, conn=conn)
        notify(owner_id, "API Key dicabut", f"API Key '{row['name']}' telah dinonaktifkan.", "warning", conn=conn)
    webhooks.dispatch(owner_id, "key.revoked", {"key_id": row["id"], "name": row["name"]})
    return row


@router.delete("/{key_id}")
def revoke(key_id: str, request: Request, body: RevokeIn | None = None,
           p: Principal = Depends(require("keys:revoke"))):
    actor_type = "api_key" if p.api_key else "user"
    row = revoke_key(key_id, p.user_id, actor_type, p.actor_label, body.reason if body else None, masked_ip(request))
    return ok(serialize(row), "API Key berhasil dicabut")


@router.post("/{key_id}/regenerate")
def regenerate(key_id: str, request: Request, p: Principal = Depends(require_session)):
    with db.transaction() as conn:
        old = _get_owned(key_id, p.user_id, conn, lock=True)
        if old["status"] == "active":
            db.execute("""UPDATE api_keys SET status='revoked', revoked_at=now(), revoked_reason='regenerated'
                          WHERE id = %s""", (old["id"],), conn)
        expires_at = old["expires_at"]
        if expires_at is not None and expires_at <= dt.datetime.now(dt.timezone.utc):
            expires_at = None
        row, raw = _insert_key(conn, p.user_id, old["name"], old["description"], old["permissions"],
                               expires_at, old["rate_limit_per_minute"], rotated_from=old["id"])
        audit("key.regenerated", actor_type="user", actor_id=p.user_id, user_id=p.user_id,
              target_type="api_key", target_id=str(row["id"]), metadata={"old_key_id": str(old["id"])},
              ip_masked=masked_ip(request), conn=conn)
        notify(p.user_id, "API Key diregenerasi",
               f"API Key '{row['name']}' diganti. Key lama langsung nonaktif.", "warning", conn=conn)
    webhooks.dispatch(p.user_id, "key.regenerated", {"key_id": row["id"], "old_key_id": old["id"]})
    data = serialize(row)
    data["api_key"] = raw
    data["warning"] = "Key lama sudah tidak berlaku. Simpan key baru ini — hanya ditampilkan sekali."
    return ok(data, "API Key berhasil diregenerasi", 201)
