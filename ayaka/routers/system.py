"""Public/system endpoints: health, info, docs catalog, status page, visitor tracking, notifications."""
from __future__ import annotations

import datetime as dt
import random
import time
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from .. import __version__, db
from ..config import (ADMIN_NAME, APP_NAME, GITHUB_URL, OWNER, PERMISSIONS, SYSTEM_NAME, WEBHOOK_EVENTS,
                      WHATSAPP_CHANNEL_URL, get_settings)
from ..deps import Principal, require_session
from ..responses import ApiError, ok
from ..security import hmac_hex
from ..services import settings_store
from ..utils import client_ip, user_agent

router = APIRouter(tags=["system"])
_BOOT = time.time()


def db_check() -> dict:
    t = time.perf_counter()
    try:
        db.scalar("SELECT 1")
        return {"status": "ok", "latency_ms": round((time.perf_counter() - t) * 1000, 1)}
    except Exception as exc:
        return {"status": "down", "error": type(exc).__name__}


@router.get("/api/health")
def health():
    d = db_check()
    s = get_settings()
    data = {"status": "ok" if d["status"] == "ok" else "degraded", "service": APP_NAME, "version": __version__,
            "powered_by": SYSTEM_NAME, "database": d,
            "email_service": "configured" if s.email_configured else "not_configured",
            "uptime_seconds": int(time.time() - _BOOT)}
    if d["status"] != "ok":
        raise ApiError(503, "DATABASE_UNAVAILABLE", "Database tidak dapat dijangkau", details=data)
    return ok(data, "Server healthy")


@router.get("/api")
def info(request: Request):
    base = get_settings().base_url(request)
    return ok({"name": APP_NAME, "version": __version__, "powered_by": SYSTEM_NAME, "admin": ADMIN_NAME,
               "owner": OWNER, "base_url": base, "api_base_url": f"{base}/api",
               "authentication": {"type": "api_key", "header": "X-API-Key", "format": "ayaka_live_<secret>"},
               "documentation": f"{base}/documentation", "openapi": f"{base}/api/openapi.json",
               "links": {"github": GITHUB_URL, "whatsapp_channel": WHATSAPP_CHANNEL_URL}}, "AYAKA API is running")


ENDPOINTS = [
    ("GET", "/api/health", "none", None, "Status server & database"),
    ("GET", "/api", "none", None, "Informasi API"),
    ("GET", "/api/docs", "none", None, "Katalog dokumentasi endpoint"),
    ("GET", "/api/user/profile", "api_key|session", "profile:read", "Profil pemilik API Key"),
    ("GET", "/api/keys", "api_key|session", "keys:read", "Daftar API Key (metadata, tanpa secret)"),
    ("POST", "/api/keys/generate", "session", None, "Generate API Key baru"),
    ("GET", "/api/keys/{id}", "api_key|session", "keys:read", "Detail API Key"),
    ("PATCH", "/api/keys/{id}", "session", None, "Ubah nama/deskripsi/permission/rate limit"),
    ("DELETE", "/api/keys/{id}", "api_key|session", "keys:revoke", "Revoke API Key"),
    ("POST", "/api/keys/{id}/regenerate", "session", None, "Regenerate API Key"),
    ("GET", "/api/analytics", "api_key|session", "analytics:read", "Statistik penggunaan akun"),
    ("GET", "/api/user/usage", "api_key|session", "analytics:read", "Pemakaian kuota bulanan"),
    ("GET", "/api/logs", "api_key|session", "logs:read", "Riwayat request (filter & pagination)"),
    ("GET", "/api/logs/{request_id}", "api_key|session", "logs:read", "Detail satu request"),
    ("POST", "/api/am/send", "api_key|session", "premium:send", "Kirim Magic Link Premium via email"),
    ("GET", "/api/am/verif?token=", "token", None, "Halaman konfirmasi Magic Link"),
    ("POST", "/api/am/verif", "token", None, "Verifikasi token & aktifkan Premium"),
    ("GET", "/api/am/status?email=", "api_key|session", "premium:status", "Status Premium sebuah email"),
    ("POST", "/api/am/renew", "api_key|session", "premium:renew", "Perpanjang Premium"),
    ("POST", "/api/am/revoke", "api_key|session", "premium:revoke", "Cabut Premium"),
]


@router.get("/api/docs")
def docs(request: Request):
    base = get_settings().base_url(request)
    return ok({"base_url": base, "auth_header": "X-API-Key",
               "endpoints": [{"method": m, "path": pth, "auth": a, "permission": perm, "description": d}
                             for m, pth, a, perm, d in ENDPOINTS],
               "permissions": PERMISSIONS, "webhook_events": WEBHOOK_EVENTS,
               "response_format": {"success": True, "message": "Request successful", "data": {},
                                   "timestamp": "2026-11-16T10:00:00Z"},
               "error_format": {"success": False, "message": "Invalid API Key",
                                "error": {"code": "INVALID_API_KEY"}},
               "openapi": f"{base}/api/openapi.json", "swagger_ui": f"{base}/api/swagger"})


@router.get("/api/system/status")
def system_status(request: Request):
    m = settings_store.maintenance_state()
    ann = db.fetchall("""SELECT id, title, body, level, created_at FROM announcements
                         WHERE is_active ORDER BY created_at DESC LIMIT 3""")
    return ok({"maintenance": {"active": m["active"], "scheduled": m["scheduled"], "message": m.get("message"),
                               "start_at": m.get("start_at"), "end_at": m.get("end_at")},
               "announcements": ann,
               "registration_open": (settings_store.get("registration") or {}).get("open", True)})


@router.get("/api/status")
def status_page():
    d = db_check()
    s = get_settings()
    w = db.fetchone("""SELECT count(*) AS total, count(*) FILTER (WHERE status_code < 500) AS ok_count,
                              coalesce(round(avg(response_time_ms)),0) AS avg_ms
                         FROM api_request_logs WHERE created_at > now() - interval '24 hours'""") if d["status"] == "ok" else None
    daily = db.fetchall(
        """SELECT d::date AS day, count(l.id) AS total, count(l.id) FILTER (WHERE l.status_code >= 500) AS errors
             FROM generate_series(date_trunc('day', now()) - interval '29 days', date_trunc('day', now()), interval '1 day') d
        LEFT JOIN api_request_logs l ON l.created_at >= d AND l.created_at < d + interval '1 day'
         GROUP BY d ORDER BY d""") if d["status"] == "ok" else []
    uptime = round(100 * w["ok_count"] / w["total"], 2) if w and w["total"] else 100.0
    m = settings_store.maintenance_state() if d["status"] == "ok" else {"active": False}
    return ok({"overall": "maintenance" if m.get("active") else ("operational" if d["status"] == "ok" else "outage"),
               "components": {"api": "operational", "database": d["status"],
                              "email": "configured" if s.email_configured else "not_configured"},
               "last_24h": {"requests": w["total"] if w else 0, "success_rate": uptime,
                            "avg_response_ms": w["avg_ms"] if w else 0},
               "daily": daily, "maintenance": m})


class TrackIn(BaseModel):
    path: str = Field(max_length=200)
    referrer: str | None = Field(default=None, max_length=500)


@router.post("/api/track")
def track(body: TrackIn, request: Request):
    """Privacy-friendly visitor counting.
    visitor_hash = HMAC(SECRET_KEY, UTC-day | IP | User-Agent): rotates daily, cannot be reversed to an IP,
    no cookie is set. Refreshes on the same day update page_views, not unique visitors.
    Do-Not-Track / Global Privacy Control are honored. Rows older than 90 days are purged."""
    if request.headers.get("dnt") == "1" or request.headers.get("sec-gpc") == "1":
        return ok({"tracked": False}, "Do-Not-Track honored")
    day = dt.datetime.now(dt.timezone.utc).date()
    vh = hmac_hex(get_settings().secret_key, f"{day.isoformat()}|{client_ip(request)}|{user_agent(request)}")
    path = body.path if body.path.startswith("/") else "/" + body.path
    path = path.split("?")[0].split("#")[0][:200]
    ref = None
    if body.referrer:
        try:
            ref = (urlparse(body.referrer).hostname or "")[:120] or None
        except ValueError:
            ref = None
    db.execute(
        """INSERT INTO visitor_analytics (visitor_hash, visit_day, path, referrer_host) VALUES (%s, %s, %s, %s)
           ON CONFLICT (visitor_hash, visit_day, path) DO UPDATE
           SET page_views = visitor_analytics.page_views + 1, updated_at = now()""", (vh, day, path, ref))
    if random.random() < 0.01:
        s = get_settings()
        db.execute("DELETE FROM visitor_analytics WHERE visit_day < (now() AT TIME ZONE 'UTC')::date - %s",
                   (s.visitor_retention_days,))
        db.execute("DELETE FROM api_request_logs WHERE created_at < now() - make_interval(days => %s)",
                   (s.log_retention_days,))
    return ok({"tracked": True})


@router.get("/api/notifications")
def notifications(p: Principal = Depends(require_session)):
    rows = db.fetchall("""SELECT id, kind, title, body, read_at, created_at FROM notifications
                          WHERE user_id=%s ORDER BY created_at DESC LIMIT 30""", (p.user_id,))
    unread = db.scalar("SELECT count(*) FROM notifications WHERE user_id=%s AND read_at IS NULL", (p.user_id,))
    ann = db.fetchall("""SELECT id, title, body, level, created_at FROM announcements WHERE is_active
                         ORDER BY created_at DESC LIMIT 5""")
    return ok({"items": rows, "unread": unread, "announcements": ann})


@router.post("/api/notifications/read-all")
def read_all(p: Principal = Depends(require_session)):
    n = db.execute("UPDATE notifications SET read_at=now() WHERE user_id=%s AND read_at IS NULL", (p.user_id,))
    return ok({"updated": n}, "Semua notifikasi ditandai dibaca")


@router.post("/api/notifications/{nid}/read")
def read_one(nid: int, p: Principal = Depends(require_session)):
    db.execute("UPDATE notifications SET read_at=now() WHERE id=%s AND user_id=%s", (nid, p.user_id))
    return ok({}, "Notifikasi dibaca")


@router.get("/api/stats/public")
def public_stats():
    """Aggregated, non-identifying platform counters for the landing page (live from DB)."""
    row = db.fetchone(
        """SELECT (SELECT count(*) FROM users) AS users,
                  (SELECT count(*) FROM api_keys) AS api_keys,
                  (SELECT count(*) FROM api_request_logs) AS requests,
                  (SELECT count(*) FROM premium_renewal_logs WHERE action = 'activate') AS premium_activations,
                  (SELECT count(DISTINCT (visitor_hash, visit_day)) FROM visitor_analytics) AS visitors""")
    return ok(row)
