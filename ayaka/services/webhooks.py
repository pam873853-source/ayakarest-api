"""Outgoing webhooks, signed with HMAC-SHA256.

Delivered synchronously with a short timeout (serverless functions cannot run
background workers after the response). Destination URLs are validated against
SSRF (private / loopback / link-local addresses are rejected).
"""
from __future__ import annotations

import ipaddress
import json
import logging
import socket
import time
import uuid
from urllib.parse import urlparse

import httpx

from .. import db
from ..config import get_settings
from ..responses import jsonable, now_iso
from ..security import decrypt_secret, hmac_hex

log = logging.getLogger("ayaka.webhooks")


def validate_url(url: str) -> str | None:
    """Returns an error message, or None when the URL is acceptable."""
    try:
        p = urlparse(url)
    except ValueError:
        return "URL tidak valid"
    allow_http = get_settings().environment == "development"
    if p.scheme != "https" and not (allow_http and p.scheme == "http"):
        return "Webhook URL wajib menggunakan HTTPS"
    if not p.hostname:
        return "Hostname tidak valid"
    try:
        infos = socket.getaddrinfo(p.hostname, p.port or (443 if p.scheme == "https" else 80))
    except socket.gaierror:
        return "Hostname tidak dapat di-resolve"
    if not allow_http:
        for info in infos:
            ip = ipaddress.ip_address(info[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                return "Webhook URL tidak boleh mengarah ke jaringan privat"
    return None


def sign(secret: str, timestamp: str, body: str) -> str:
    return "sha256=" + hmac_hex(secret, f"{timestamp}.{body}")


def deliver(hook: dict, event: str, data: dict) -> tuple[int | None, str | None]:
    secret = decrypt_secret(hook["secret_encrypted"])
    if secret is None:
        return None, "Secret tidak dapat didekripsi (SECRET_KEY berubah?)"
    body = json.dumps({"id": f"evt_{uuid.uuid4().hex}", "event": event, "created_at": now_iso(),
                       "data": jsonable(data)}, separators=(",", ":"))
    ts = str(int(time.time()))
    status, err = None, None
    try:
        r = httpx.post(hook["url"], content=body, timeout=3.0, follow_redirects=False,
                       headers={"Content-Type": "application/json", "User-Agent": "AYAKA-Sync-Webhook/1.0",
                                "X-Ayaka-Event": event, "X-Ayaka-Timestamp": ts,
                                "X-Ayaka-Signature": sign(secret, ts, body)})
        status = r.status_code
        if status >= 400:
            err = f"HTTP {status}"
    except httpx.HTTPError as exc:
        err = f"{type(exc).__name__}"
    db.execute(
        """UPDATE webhook_configs SET last_status_code=%s, last_delivery_at=now(), last_error=%s,
                  failure_count = CASE WHEN %s THEN 0 ELSE failure_count + 1 END WHERE id=%s""",
        (status, err, err is None, hook["id"]))
    return status, err


def dispatch(owner_id: str, event: str, data: dict) -> None:
    try:
        hooks = db.fetchall(
            "SELECT * FROM webhook_configs WHERE owner_id=%s AND is_active AND %s = ANY(events)",
            (owner_id, event))
        for h in hooks[:5]:
            deliver(h, event, data)
    except Exception:
        log.exception("webhook dispatch failed")
