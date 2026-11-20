"""AYAKA Sync admin panel API. Access requires a session whose user has a row in
admin_users (role stored in DB). Email alone is never treated as authorization."""
from __future__ import annotations

import datetime as dt
import os
import platform
import sys
import time
import uuid

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from .. import __version__, db
from ..config import ADMIN_NAME, OWNER, get_settings
from ..deps import Principal, require_admin
from ..responses import ApiError, ok
from ..services import analytics, settings_store
from ..services.activity import audit, notify
from ..services.resend_client import check_resend
from ..utils import masked_ip, public_user
from . import keys as keys_router
from . import system
from .logs import query_logs

router = APIRouter(prefix="/api/admin", tags=["admin"])
_BOOT = time.time()


def _uid(v: str) -> str:
    try:
        return str(uuid.UUID(v))
    except ValueError:
        raise ApiError(404, "USER_NOT_FOUND", "Pengguna tidak ditemukan")


def _log(p: Principal, request: Request, action: str, target_type=None, target_id=None, meta=None, user_id=None):
    audit(action, actor_type="admin", actor_id=p.user_id, user_id=user_id, target_type=target_type,
          target_id=target_id, metadata=meta, ip_masked=masked_ip(request))


@router.get("/overview")
def overview(p: Principal = Depends(require_admin)):
    t = analytics.build(None)["totals"]
    t["users_suspended"] = db.scalar("SELECT count(*) FROM users WHERE status='suspended'")
    t["users_today"] = db.scalar("SELECT count(*) FROM users WHERE created_at > date_trunc('day', now())")
    t["premium_total"] = db.scalar("SELECT count(*) FROM premium_subscriptions")
    return ok({"identity": {"admin": ADMIN_NAME, "owner": OWNER, "email": get_settings().admin_email,
                            "you": public_user(p.user), "role": p.admin_role},
               "totals": t,
               "maintenance": settings_store.maintenance_state()})


@router.get("/analytics")
def admin_analytics(p: Principal = Depends(require_admin)):
    return ok(analytics.build(None))


@router.get("/users")
def users(p: Principal = Depends(require_admin), q: str | None = Query(None, max_length=100),
          status: str | None = Query(None, pattern="^(active|suspended)$"),
          page: int = Query(1, ge=1), per_page: int = Query(20, ge=1, le=100)):
    where, params = [], []
    if q:
        where.append("(u.email ILIKE %s OR u.username ILIKE %s OR u.full_name ILIKE %s)"); params += [f"%{q}%"] * 3
    if status:
        where.append("u.status = %s"); params.append(status)
    w = ("WHERE " + " AND ".join(where)) if where else ""
    total = db.scalar(f"SELECT count(*) FROM users u {w}", params)
    rows = db.fetchall(
        f"""SELECT u.id, u.username, u.full_name, u.email, u.status, u.monthly_quota, u.created_at, u.last_login_at,
                   a.role AS admin_role,
                   (SELECT count(*) FROM api_keys k WHERE k.owner_id = u.id) AS key_count,
                   (SELECT count(*) FROM api_request_logs l WHERE l.user_id = u.id) AS request_count
              FROM users u LEFT JOIN admin_users a ON a.user_id = u.id {w}
             ORDER BY u.created_at DESC LIMIT %s OFFSET %s""", params + [per_page, (page - 1) * per_page])
    return ok({"items": rows, "total": total, "page": page, "per_page": per_page,
               "pages": max(1, -(-total // per_page))})


@router.get("/users/{user_id}")
def user_detail(user_id: str, p: Principal = Depends(require_admin)):
    u = db.fetchone("""SELECT u.*, a.role AS admin_role FROM users u LEFT JOIN admin_users a ON a.user_id=u.id
                       WHERE u.id=%s""", (_uid(user_id),))
    if not u:
        raise ApiError(404, "USER_NOT_FOUND", "Pengguna tidak ditemukan")
    keys = db.fetchall(f"SELECT {keys_router.KEY_COLUMNS} FROM api_keys WHERE owner_id=%s ORDER BY created_at DESC",
                       (u["id"],))
    stats = db.fetchone("""SELECT count(*) AS requests, count(*) FILTER (WHERE status_code>=400) AS failed
                           FROM api_request_logs WHERE user_id=%s""", (u["id"],))
    premium = db.scalar("SELECT count(*) FROM premium_subscriptions WHERE owner_id=%s", (u["id"],))
    activity = db.fetchall("""SELECT action, actor_type, target_type, target_id, created_at FROM audit_logs
                              WHERE user_id=%s ORDER BY created_at DESC LIMIT 20""", (u["id"],))
    data = public_user(u)
    data.update({"admin_role": u["admin_role"], "failed_login_count": u["failed_login_count"],
                 "locked_until": u["locked_until"], "keys": [keys_router.serialize(k) for k in keys],
                 "stats": stats, "premium_customers": premium, "activity": activity})
    return ok(data)


class StatusIn(BaseModel):
    reason: str | None = Field(default=None, max_length=200)


def _set_status(user_id: str, status: str, p: Principal, request: Request, reason: str | None):
    uid = _uid(user_id)
    if uid == p.user_id:
        raise ApiError(400, "CANNOT_MODIFY_SELF", "Tidak dapat mengubah status akun sendiri")
    if status == "suspended" and db.fetchone("SELECT 1 FROM admin_users WHERE user_id=%s", (uid,)):
        raise ApiError(403, "CANNOT_SUSPEND_ADMIN", "Akun administrator tidak dapat ditangguhkan dari panel")
    with db.transaction() as conn:
        u = db.fetchone("UPDATE users SET status=%s WHERE id=%s RETURNING *", (status, uid), conn)
        if not u:
            raise ApiError(404, "USER_NOT_FOUND", "Pengguna tidak ditemukan")
        if status == "suspended":
            db.execute("UPDATE user_sessions SET revoked_at=now() WHERE user_id=%s AND revoked_at IS NULL", (uid,), conn)
        audit(f"admin.user_{'suspended' if status == 'suspended' else 'activated'}", actor_type="admin",
              actor_id=p.user_id, user_id=uid, target_type="user", target_id=uid, metadata={"reason": reason},
              ip_masked=masked_ip(request), conn=conn)
        if status == "active":
            notify(uid, "Akun diaktifkan kembali", "Administrator mengaktifkan akun Anda.", "success", conn=conn)
    return u


@router.post("/users/{user_id}/suspend")
def suspend(user_id: str, request: Request, body: StatusIn | None = None, p: Principal = Depends(require_admin)):
    u = _set_status(user_id, "suspended", p, request, body.reason if body else None)
    return ok(public_user(u), "Pengguna ditangguhkan")


@router.post("/users/{user_id}/activate")
def activate(user_id: str, request: Request, p: Principal = Depends(require_admin)):
    u = _set_status(user_id, "active", p, request, None)
    return ok(public_user(u), "Pengguna diaktifkan")


class DeleteIn(BaseModel):
    confirm_email: str = Field(max_length=254)


@router.delete("/users/{user_id}")
def delete_user(user_id: str, body: DeleteIn, request: Request, p: Principal = Depends(require_admin)):
    uid = _uid(user_id)
    if uid == p.user_id:
        raise ApiError(400, "CANNOT_DELETE_SELF", "Tidak dapat menghapus akun sendiri")
    u = db.fetchone("SELECT * FROM users WHERE id=%s", (uid,))
    if not u:
        raise ApiError(404, "USER_NOT_FOUND", "Pengguna tidak ditemukan")
    if db.fetchone("SELECT 1 FROM admin_users WHERE user_id=%s", (uid,)):
        raise ApiError(403, "CANNOT_DELETE_ADMIN", "Akun administrator tidak dapat dihapus dari panel")
    if body.confirm_email.strip().lower() != u["email"].lower():
        raise ApiError(422, "CONFIRMATION_MISMATCH", "Email konfirmasi tidak cocok")
    with db.transaction() as conn:
        audit("admin.user_deleted", actor_type="admin", actor_id=p.user_id, target_type="user", target_id=uid,
              metadata={"email": u["email"], "username": u["username"]}, ip_masked=masked_ip(request), conn=conn)
        db.execute("DELETE FROM users WHERE id=%s", (uid,), conn)
    return ok({"deleted": uid}, "Pengguna dihapus permanen")


@router.get("/keys")
def all_keys(p: Principal = Depends(require_admin), q: str | None = Query(None, max_length=100),
             page: int = Query(1, ge=1), per_page: int = Query(25, ge=1, le=100)):
    params, w = [], ""
    if q:
        w = "WHERE k.name ILIKE %s OR u.email ILIKE %s OR k.key_prefix || k.key_last4 ILIKE %s"
        params = [f"%{q}%"] * 3
    total = db.scalar(f"SELECT count(*) FROM api_keys k JOIN users u ON u.id=k.owner_id {w}", params)
    rows = db.fetchall(
        f"""SELECT {', '.join('k.' + c.strip() for c in keys_router.KEY_COLUMNS.split(','))}, u.email AS owner_email
              FROM api_keys k JOIN users u ON u.id=k.owner_id {w}
             ORDER BY k.created_at DESC LIMIT %s OFFSET %s""", params + [per_page, (page - 1) * per_page])
    items = []
    for r in rows:
        d = keys_router.serialize(r)
        d["owner_email"] = r["owner_email"]
        d["owner_id"] = r["owner_id"]
        items.append(d)
    return ok({"items": items, "total": total, "page": page, "per_page": per_page,
               "pages": max(1, -(-total // per_page))})


class AdminRevokeIn(BaseModel):
    reason: str = Field(default="revoked by administrator", max_length=120)


@router.post("/keys/{key_id}/revoke")
def admin_revoke_key(key_id: str, request: Request, body: AdminRevokeIn | None = None,
                     p: Principal = Depends(require_admin)):
    try:
        kid = str(uuid.UUID(key_id))
    except ValueError:
        raise ApiError(404, "KEY_NOT_FOUND", "API Key tidak ditemukan")
    owner = db.scalar("SELECT owner_id FROM api_keys WHERE id=%s", (kid,))
    if not owner:
        raise ApiError(404, "KEY_NOT_FOUND", "API Key tidak ditemukan")
    row = keys_router.revoke_key(kid, str(owner), "admin", p.user_id,
                                 (body.reason if body else "revoked by administrator"), masked_ip(request))
    return ok(keys_router.serialize(row), "API Key dicabut oleh admin")


@router.get("/audit")
def audit_logs(p: Principal = Depends(require_admin), action: str | None = Query(None, max_length=64),
               actor_type: str | None = Query(None, max_length=16), q: str | None = Query(None, max_length=100),
               page: int = Query(1, ge=1), per_page: int = Query(30, ge=1, le=100)):
    where, params = [], []
    if action:
        where.append("a.action ILIKE %s"); params.append(f"%{action}%")
    if actor_type:
        where.append("a.actor_type = %s"); params.append(actor_type)
    if q:
        where.append("(a.target_id ILIKE %s OR u.email ILIKE %s OR a.action ILIKE %s)"); params += [f"%{q}%"] * 3
    w = ("WHERE " + " AND ".join(where)) if where else ""
    total = db.scalar(f"SELECT count(*) FROM audit_logs a LEFT JOIN users u ON u.id=a.user_id {w}", params)
    rows = db.fetchall(
        f"""SELECT a.id, a.actor_type, a.actor_id, a.action, a.target_type, a.target_id, a.metadata, a.ip_masked,
                   a.created_at, u.email AS user_email
              FROM audit_logs a LEFT JOIN users u ON u.id=a.user_id {w}
             ORDER BY a.created_at DESC LIMIT %s OFFSET %s""", params + [per_page, (page - 1) * per_page])
    return ok({"items": rows, "total": total, "page": page, "per_page": per_page,
               "pages": max(1, -(-total // per_page))})


@router.get("/logs")
def admin_logs(p: Principal = Depends(require_admin), endpoint: str | None = None, status: str | None = None,
               q: str | None = None, page: int = Query(1, ge=1), per_page: int = Query(25, ge=1, le=100)):
    return ok(query_logs(None, endpoint, status, None, None, q, page, per_page))


@router.get("/monitoring")
def monitoring(p: Principal = Depends(require_admin)):
    s = get_settings()
    dbc = system.db_check()
    db_info = {}
    if dbc["status"] == "ok":
        db_info = db.fetchone(
            """SELECT version() AS version, pg_size_pretty(pg_database_size(current_database())) AS size,
                      current_database() AS name,
                      (SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()) AS connections""")
        db_info["tables"] = db.fetchall(
            """SELECT relname AS table, n_live_tup AS rows FROM pg_stat_user_tables ORDER BY relname""")
    pool = {}
    try:
        st = db.get_pool().get_stats()
        pool = {k: st.get(k) for k in ("pool_min", "pool_max", "pool_size", "pool_available", "requests_num")}
    except Exception:
        pass
    email = db.fetchone("""SELECT count(*) FILTER (WHERE status='sent') AS sent,
                                  count(*) FILTER (WHERE status='failed') AS failed,
                                  max(created_at) FILTER (WHERE status='sent') AS last_sent,
                                  (array_agg(error ORDER BY created_at DESC) FILTER (WHERE status='failed'))[1] AS last_error
                             FROM email_logs WHERE created_at > now() - interval '24 hours'""")
    errors = db.fetchall("""SELECT endpoint, status_code, error_code, count(*) AS n, max(created_at) AS last_seen
                              FROM api_request_logs WHERE status_code >= 500 AND created_at > now() - interval '24 hours'
                             GROUP BY endpoint, status_code, error_code ORDER BY n DESC LIMIT 10""")
    return ok({
        "server": {"status": "ok", "version": __version__, "python": sys.version.split()[0],
                   "platform": platform.platform(), "environment": s.environment,
                   "region": os.getenv("VERCEL_REGION", "local"), "instance_uptime_s": int(time.time() - _BOOT),
                   "base_url": s.base_url()},
        "database": {**dbc, **db_info, "pool": pool},
        "email": {**check_resend(), "from": s.email_from or None, "last_24h": email},
        "errors_24h": errors,
        "checked_at": dt.datetime.now(dt.timezone.utc),
    })


class MaintenanceIn(BaseModel):
    enabled: bool
    message: str = Field(default="AYAKA API sedang dalam pemeliharaan terjadwal.", max_length=500)
    start_at: str | None = None
    end_at: str | None = None


class SettingsIn(BaseModel):
    registration_open: bool | None = None
    default_rate_limit_per_minute: int | None = Field(default=None, ge=1, le=1000)
    default_monthly_quota: int | None = Field(default=None, ge=0, le=100_000_000)


@router.get("/settings")
def get_settings_(p: Principal = Depends(require_admin)):
    settings_store.clear_cache()
    return ok({"maintenance": settings_store.maintenance_state(),
               "registration": settings_store.get("registration"),
               "defaults": settings_store.get("defaults")})


@router.put("/maintenance")
def set_maintenance(body: MaintenanceIn, request: Request, p: Principal = Depends(require_admin)):
    for f in (body.start_at, body.end_at):
        if f:
            try:
                dt.datetime.fromisoformat(f.replace("Z", "+00:00"))
            except ValueError:
                raise ApiError(422, "INVALID_DATE", "Format jadwal harus ISO 8601")
    value = body.model_dump()
    settings_store.set_value("maintenance", value, p.user_id)
    _log(p, request, "admin.maintenance_" + ("enabled" if body.enabled else "disabled"), "setting", "maintenance", value)
    return ok(settings_store.maintenance_state(), "Maintenance Mode diperbarui")


@router.put("/settings")
def put_settings(body: SettingsIn, request: Request, p: Principal = Depends(require_admin)):
    if body.registration_open is not None:
        settings_store.set_value("registration", {"open": body.registration_open}, p.user_id)
    d = dict(settings_store.get("defaults") or {})
    if body.default_rate_limit_per_minute is not None:
        d["rate_limit_per_minute"] = body.default_rate_limit_per_minute
    if body.default_monthly_quota is not None:
        d["monthly_quota"] = body.default_monthly_quota
    settings_store.set_value("defaults", d, p.user_id)
    _log(p, request, "admin.settings_updated", "setting", "system", body.model_dump(exclude_none=True))
    return ok({"registration": settings_store.get("registration"), "defaults": settings_store.get("defaults")},
              "Pengaturan sistem disimpan")


class QuotaIn(BaseModel):
    monthly_quota: int = Field(ge=0, le=100_000_000)


@router.put("/users/{user_id}/quota")
def set_quota(user_id: str, body: QuotaIn, request: Request, p: Principal = Depends(require_admin)):
    uid = _uid(user_id)
    u = db.fetchone("UPDATE users SET monthly_quota=%s WHERE id=%s RETURNING *", (body.monthly_quota, uid))
    if not u:
        raise ApiError(404, "USER_NOT_FOUND", "Pengguna tidak ditemukan")
    _log(p, request, "admin.quota_updated", "user", uid, {"monthly_quota": body.monthly_quota}, uid)
    return ok(public_user(u), "Kuota diperbarui")


class AnnouncementIn(BaseModel):
    title: str = Field(min_length=3, max_length=120)
    body: str = Field(min_length=3, max_length=1000)
    level: str = Field(default="info", pattern="^(info|warning|critical)$")
    is_active: bool = True


@router.get("/announcements")
def list_ann(p: Principal = Depends(require_admin)):
    return ok({"items": db.fetchall("SELECT * FROM announcements ORDER BY created_at DESC LIMIT 50")})


@router.post("/announcements")
def create_ann(body: AnnouncementIn, request: Request, p: Principal = Depends(require_admin)):
    row = db.fetchone("""INSERT INTO announcements (title, body, level, is_active, created_by)
                         VALUES (%s,%s,%s,%s,%s) RETURNING *""",
                      (body.title, body.body, body.level, body.is_active, p.user_id))
    _log(p, request, "admin.announcement_created", "announcement", str(row["id"]), {"title": body.title})
    return ok(row, "Pengumuman dipublikasikan", 201)


@router.patch("/announcements/{ann_id}")
def toggle_ann(ann_id: str, request: Request, p: Principal = Depends(require_admin)):
    try:
        row = db.fetchone("UPDATE announcements SET is_active = NOT is_active WHERE id=%s RETURNING *",
                          (str(uuid.UUID(ann_id)),))
    except ValueError:
        row = None
    if not row:
        raise ApiError(404, "NOT_FOUND", "Pengumuman tidak ditemukan")
    _log(p, request, "admin.announcement_toggled", "announcement", ann_id, {"is_active": row["is_active"]})
    return ok(row, "Pengumuman diperbarui")


@router.delete("/announcements/{ann_id}")
def delete_ann(ann_id: str, request: Request, p: Principal = Depends(require_admin)):
    try:
        n = db.execute("DELETE FROM announcements WHERE id=%s", (str(uuid.UUID(ann_id)),))
    except ValueError:
        n = 0
    if not n:
        raise ApiError(404, "NOT_FOUND", "Pengumuman tidak ditemukan")
    _log(p, request, "admin.announcement_deleted", "announcement", ann_id)
    return ok({}, "Pengumuman dihapus")
