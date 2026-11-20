"""Authentication & authorization middleware (FastAPI dependencies).

Two credential types:
  * Session cookie (dashboard) — HttpOnly, Secure, SameSite=Lax + CSRF header on writes.
  * X-API-Key header (third-party apps) — HMAC-hashed lookup, status/expiry/permission/rate checks.
API keys are NEVER accepted from URL query parameters.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from fastapi import Request

from . import db
from .config import get_settings
from .responses import ApiError
from .security import API_KEY_RE, constant_time_equals, hash_api_key, sha256_hex
from .services import ratelimit

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
URL_KEY_PARAMS = {"api_key", "apikey", "x-api-key", "x_api_key", "key", "token_key"}


@dataclass
class Principal:
    user: dict
    auth_type: str  # "session" | "api_key"
    session: dict | None = None
    api_key: dict | None = None
    is_admin: bool = False
    admin_role: str | None = None
    permissions: set[str] = field(default_factory=set)

    @property
    def user_id(self) -> str:
        return str(self.user["id"])

    @property
    def actor_label(self) -> str:
        if self.api_key:
            return f"api_key:{self.api_key['id']}"
        return f"user:{self.user_id}"

    def has(self, perm: str) -> bool:
        return self.auth_type == "session" or perm in self.permissions


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def load_session(request: Request) -> dict | None:
    """Returns joined session+user row or None. Cached per request."""
    if hasattr(request.state, "_session_loaded"):
        return request.state._session_row
    request.state._session_loaded = True
    request.state._session_row = None
    token = request.cookies.get(get_settings().session_cookie_name)
    if not token or len(token) > 200:
        return None
    row = db.fetchone(
        """SELECT s.id AS session_id, s.csrf_token, s.expires_at, s.last_seen_at, s.remember_me,
                  u.*, a.role AS admin_role
             FROM user_sessions s
             JOIN users u ON u.id = s.user_id
        LEFT JOIN admin_users a ON a.user_id = u.id
            WHERE s.token_hash = %s AND s.revoked_at IS NULL AND s.expires_at > now()""",
        (sha256_hex(token),),
    )
    if not row:
        return None
    if row["status"] != "active":
        return None
    if (_now() - row["last_seen_at"]).total_seconds() > 300:
        db.execute("UPDATE user_sessions SET last_seen_at = now() WHERE id = %s", (row["session_id"],))
    request.state._session_row = row
    return row


def _session_principal(row: dict) -> Principal:
    return Principal(user=row, auth_type="session", session=row,
                     is_admin=row.get("admin_role") is not None, admin_role=row.get("admin_role"))


def check_csrf(request: Request, row: dict) -> None:
    if request.method in SAFE_METHODS:
        return
    header = request.headers.get("x-csrf-token", "")
    if not header or not constant_time_equals(header, row["csrf_token"]):
        raise ApiError(403, "CSRF_TOKEN_INVALID", "CSRF token tidak valid. Muat ulang halaman.")


def reject_key_in_url(request: Request) -> None:
    if any(k.lower() in URL_KEY_PARAMS for k in request.query_params.keys()):
        raise ApiError(400, "API_KEY_IN_URL",
                       "API Key tidak boleh dikirim lewat URL. Gunakan header X-API-Key.")


def _api_key_principal(request: Request, raw: str, permission: str | None) -> Principal:
    raw = raw.strip()
    if not API_KEY_RE.match(raw):
        raise ApiError(401, "INVALID_API_KEY", "Invalid API Key")
    row = db.fetchone(
        """SELECT k.id AS key_id, k.owner_id, k.name AS key_name, k.permissions, k.status AS key_status,
                  k.expires_at AS key_expires_at, k.rate_limit_per_minute, k.key_prefix, k.key_last4,
                  u.*
             FROM api_keys k JOIN users u ON u.id = k.owner_id
            WHERE k.key_hash = %s""",
        (hash_api_key(raw),),
    )
    if not row:
        raise ApiError(401, "INVALID_API_KEY", "Invalid API Key")
    request.state.api_key_id = str(row["key_id"])
    request.state.user_id = str(row["owner_id"])
    if row["key_status"] == "revoked":
        raise ApiError(401, "API_KEY_REVOKED", "API Key telah dicabut (revoked)")
    if row["key_expires_at"] is not None and row["key_expires_at"] <= _now():
        raise ApiError(401, "API_KEY_EXPIRED", "API Key telah kedaluwarsa")
    if row["status"] != "active":
        raise ApiError(403, "ACCOUNT_SUSPENDED", "Akun pemilik API Key sedang ditangguhkan")
    perms = set(row["permissions"] or [])
    if permission and permission not in perms:
        raise ApiError(403, "INSUFFICIENT_PERMISSION",
                       f"API Key tidak memiliki permission '{permission}'",
                       details={"required": permission})
    # Per-key rate limit (per minute) and per-account monthly quota.
    limit = int(row["rate_limit_per_minute"])
    remaining = ratelimit.enforce(f"key:{row['key_id']}", limit, 60, "RATE_LIMITED",
                                  "Rate limit API Key terlampaui. Coba lagi sebentar lagi.")
    request.state.rate_headers = {"X-RateLimit-Limit": str(limit), "X-RateLimit-Remaining": str(remaining)}
    month = _now().strftime("%Y-%m")
    allowed, _, _ = ratelimit.hit(f"quota:{row['owner_id']}:{month}", int(row["monthly_quota"]), 40 * 86400)
    if not allowed:
        raise ApiError(429, "QUOTA_EXCEEDED", "Kuota bulanan akun telah habis")
    db.execute("UPDATE api_keys SET last_used_at = now(), usage_count = usage_count + 1 WHERE id = %s",
               (row["key_id"],))
    key = {"id": row["key_id"], "name": row["key_name"], "permissions": sorted(perms),
           "prefix": row["key_prefix"], "last4": row["key_last4"]}
    return Principal(user=row, auth_type="api_key", api_key=key, permissions=perms)


def authenticate(request: Request, permission: str | None = None, allow_session: bool = True,
                 allow_api_key: bool = True) -> Principal:
    reject_key_in_url(request)
    raw = request.headers.get("x-api-key")
    if raw is not None:
        if not allow_api_key:
            raise ApiError(403, "SESSION_REQUIRED",
                           "Endpoint ini hanya dapat diakses dari dashboard (login session).")
        p = _api_key_principal(request, raw, permission)
        request.state.auth_type = "api_key"
        return p
    if allow_session:
        row = load_session(request)
        if row:
            check_csrf(request, row)
            request.state.user_id = str(row["id"])
            request.state.auth_type = "session"
            return _session_principal(row)
    if allow_api_key and not allow_session:
        raise ApiError(401, "API_KEY_REQUIRED", "Header X-API-Key wajib disertakan")
    raise ApiError(401, "UNAUTHORIZED", "Autentikasi diperlukan. Login atau sertakan header X-API-Key.")


# ---- Dependency factories --------------------------------------------------

def require(permission: str | None = None, *, session_only: bool = False):
    def dep(request: Request) -> Principal:
        return authenticate(request, permission, allow_session=True, allow_api_key=not session_only)
    return dep


def require_session(request: Request) -> Principal:
    return authenticate(request, None, allow_session=True, allow_api_key=False)


def require_admin(request: Request) -> Principal:
    p = authenticate(request, None, allow_session=True, allow_api_key=False)
    if not p.is_admin:
        raise ApiError(403, "ADMIN_REQUIRED", "Akses khusus administrator AYAKA Sync")
    return p
