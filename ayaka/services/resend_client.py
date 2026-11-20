"""Resend email integration (https://resend.com/docs/api-reference/emails/send-email)."""
from __future__ import annotations

import logging

import httpx

from .. import db
from ..config import get_settings

log = logging.getLogger("ayaka.email")
RESEND_URL = "https://api.resend.com/emails"


class EmailResult:
    def __init__(self, ok: bool, provider_id: str | None = None, error: str | None = None):
        self.ok = ok
        self.provider_id = provider_id
        self.error = error


def _post(payload: dict, api_key: str) -> httpx.Response:
    return httpx.post(RESEND_URL, json=payload, timeout=10.0,
                      headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})


def send_email(to: str, subject: str, html: str, text: str, template: str,
               owner_id: str | None = None) -> EmailResult:
    s = get_settings()
    if not s.email_configured:
        result = EmailResult(False, error="Email service not configured (RESEND_API_KEY / EMAIL_FROM)")
    else:
        try:
            resp = _post({"from": s.email_from, "to": [to], "subject": subject, "html": html,
                          "text": text}, s.resend_api_key)
            if 200 <= resp.status_code < 300:
                result = EmailResult(True, provider_id=(resp.json() or {}).get("id"))
            else:
                # Resend error bodies contain only a message/name — never our key.
                try:
                    msg = (resp.json() or {}).get("message", "")
                except ValueError:
                    msg = ""
                result = EmailResult(False, error=f"Resend HTTP {resp.status_code}: {msg}"[:300])
        except httpx.HTTPError as exc:
            result = EmailResult(False, error=f"Resend connection error: {type(exc).__name__}")
    try:
        db.execute(
            "INSERT INTO email_logs (owner_id, to_email, template, status, provider_id, error) VALUES (%s,%s,%s,%s,%s,%s)",
            (owner_id, to, template, "sent" if result.ok else "failed", result.provider_id, result.error))
    except Exception:  # logging must never break the request
        log.exception("failed to write email log")
    if not result.ok:
        log.warning("email send failed template=%s error=%s", template, result.error)
    return result


def check_resend() -> dict:
    """Lightweight connectivity check used by the admin monitor."""
    s = get_settings()
    if not s.email_configured:
        return {"status": "not_configured", "detail": "RESEND_API_KEY / EMAIL_FROM belum diatur"}
    try:
        r = httpx.get("https://api.resend.com/domains", timeout=6.0,
                      headers={"Authorization": f"Bearer {s.resend_api_key}"})
        if r.status_code == 200:
            domains = [{"name": d.get("name"), "status": d.get("status")} for d in (r.json().get("data") or [])]
            return {"status": "ok", "detail": "Resend API reachable", "domains": domains}
        if r.status_code in (401, 403):
            # Sending-only keys cannot list domains; reachable but restricted.
            return {"status": "ok", "detail": "Reachable (sending-only key, domain list restricted)"}
        return {"status": "degraded", "detail": f"Resend HTTP {r.status_code}"}
    except httpx.HTTPError as exc:
        return {"status": "down", "detail": f"Connection error: {type(exc).__name__}"}
