"""Global HTTP middleware: request id, body size limit, maintenance mode,
security headers and privacy-safe request logging."""
from __future__ import annotations

import logging
import time
import uuid

from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from . import db
from .config import get_settings
from .deps import load_session
from .responses import error_response
from .services import settings_store
from .utils import masked_ip, user_agent

log = logging.getLogger("ayaka.middleware")

# Paths that stay reachable during maintenance.
MAINTENANCE_ALLOW = ("/api/health", "/api/system/status", "/api/status", "/api/auth/login",
                     "/api/auth/logout", "/api/auth/me", "/api/admin", "/api/track")
# Internal dashboard polling is not counted as API traffic unless an API key is used.
NO_LOG_PREFIX = ("/api/analytics", "/api/track", "/api/notifications", "/api/system/status",
                 "/api/auth/me", "/api/admin/analytics", "/api/admin/monitoring", "/api/health",
                 "/api/stats/public", "/api/status")

HTML_CSP = ("default-src 'self'; script-src 'self' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com data:; img-src 'self' data:; "
            "connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'")


SWAGGER_CSP = ("default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
               "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; img-src 'self' data: https://fastapi.tiangolo.com; "
               "connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; object-src 'none'")


def _apply_security_headers(response, request_id: str, path: str = "") -> None:
    h = response.headers
    h["X-Request-ID"] = request_id
    h["X-Content-Type-Options"] = "nosniff"
    h["X-Frame-Options"] = "DENY"
    h["Referrer-Policy"] = "strict-origin-when-cross-origin"
    h["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=()"
    h["Cross-Origin-Opener-Policy"] = "same-origin"
    if get_settings().cookie_secure:
        h["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
    ctype = h.get("content-type", "")
    if ctype.startswith("text/html"):
        h["Content-Security-Policy"] = SWAGGER_CSP if path == "/api/swagger" else HTML_CSP
    else:
        h.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
    if h.get("content-type", "").startswith("application/json"):
        h.setdefault("Cache-Control", "no-store")


def _write_log(entry: dict) -> None:
    try:
        db.execute(
            """INSERT INTO api_request_logs (request_id, user_id, api_key_id, auth_type, method, endpoint,
                   status_code, response_time_ms, ip_masked, user_agent, error_code)
               VALUES (%(request_id)s, %(user_id)s, %(api_key_id)s, %(auth_type)s, %(method)s, %(endpoint)s,
                   %(status_code)s, %(response_time_ms)s, %(ip_masked)s, %(user_agent)s, %(error_code)s)
               ON CONFLICT (request_id) DO NOTHING""", entry)
    except Exception:
        log.exception("request log write failed")


def _maintenance_block(request: Request) -> bool:
    state = settings_store.maintenance_state()
    if not state.get("active"):
        return False
    row = load_session(request)
    return not (row and row.get("admin_role"))


class AyakaMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = "req_" + uuid.uuid4().hex[:24]
        request.state.request_id = request_id
        start = time.perf_counter()
        path = request.url.path
        is_api = path == "/api" or path.startswith("/api/")
        s = get_settings()

        cl = request.headers.get("content-length")
        if cl and cl.isdigit() and int(cl) > s.max_body_bytes:
            resp = error_response(413, "PAYLOAD_TOO_LARGE", "Ukuran request melebihi batas 1 MB")
            _apply_security_headers(resp, request_id, request.url.path)
            return resp

        if is_api and not path.startswith(MAINTENANCE_ALLOW) and request.method != "OPTIONS":
            try:
                blocked = await run_in_threadpool(_maintenance_block, request)
            except Exception:
                blocked = False
            if blocked:
                m = settings_store.maintenance_state()
                resp = error_response(503, "MAINTENANCE_MODE", m.get("message") or "Maintenance",
                                      details={"end_at": m.get("end_at")}, headers={"Retry-After": "300"})
                _apply_security_headers(resp, request_id, request.url.path)
                return resp

        response = await call_next(request)
        elapsed = int((time.perf_counter() - start) * 1000)
        _apply_security_headers(response, request_id, request.url.path)
        response.headers["X-Response-Time"] = f"{elapsed}ms"
        if path.startswith(("/css/", "/js/", "/assets/")):
            response.headers["Cache-Control"] = "public, max-age=0, must-revalidate"
        for k, v in (getattr(request.state, "rate_headers", None) or {}).items():
            response.headers[k] = v

        auth_type = getattr(request.state, "auth_type", "none")
        if is_api and request.method != "OPTIONS" and (
                auth_type == "api_key" or getattr(request.state, "api_key_id", None)
                or not path.startswith(NO_LOG_PREFIX)):
            entry = {
                "request_id": request_id,
                "user_id": getattr(request.state, "user_id", None),
                "api_key_id": getattr(request.state, "api_key_id", None),
                "auth_type": auth_type,
                "method": request.method,
                "endpoint": path[:200],  # path only — query strings (tokens) are never logged
                "status_code": response.status_code,
                "response_time_ms": elapsed,
                "ip_masked": masked_ip(request),
                "user_agent": user_agent(request),
                "error_code": getattr(request.state, "error_code", None),
            }
            await run_in_threadpool(_write_log, entry)
        return response
