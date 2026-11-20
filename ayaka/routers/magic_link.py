"""Magic Link Premium: /api/am/send, /verif, /status, /renew, /revoke.

Multi-tenant: every subscription belongs to the API owner (owner_id) whose key
created it, so one owner can never read or mutate another owner's customers.
"""
from __future__ import annotations

import datetime as dt
from html import escape

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from .. import db
from ..config import get_settings
from ..deps import Principal, require, require_session
from ..responses import ApiError, ok
from ..security import generate_token, sha256_hex
from ..services import email_templates, ratelimit, webhooks
from ..services.activity import audit, notify
from ..services.resend_client import send_email
from .auth import normalize_email

router = APIRouter(prefix="/api/am", tags=["magic-link-premium"])
premium_router = APIRouter(prefix="/api/premium", tags=["magic-link-premium"])

PLANS = {"premium": 30, "premium_quarterly": 90, "premium_yearly": 365}


class SendIn(BaseModel):
    email: str = Field(max_length=254)
    plan: str = Field(default="premium", max_length=32)
    duration_days: int | None = Field(default=None, ge=1, le=365)
    name: str | None = Field(default=None, max_length=80)


class VerifyIn(BaseModel):
    token: str = Field(min_length=20, max_length=200)


class RenewIn(BaseModel):
    email: str = Field(max_length=254)
    duration_days: int = Field(ge=1, le=365)


class RevokeIn(BaseModel):
    email: str = Field(max_length=254)
    reason: str | None = Field(default=None, max_length=200)


def _fmt(ts: dt.datetime) -> str:
    return ts.astimezone(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _status_of(sub: dict | None) -> str:
    if not sub:
        return "none"
    if sub["status"] == "revoked":
        return "revoked"
    if sub["expires_at"] <= dt.datetime.now(dt.timezone.utc):
        return "expired"
    return "active"


def _sub_payload(email: str, sub: dict | None) -> dict:
    st = _status_of(sub)
    return {"email": email, "premium": st == "active", "status": st,
            "plan": sub["plan"] if sub else None,
            "activated_at": sub["activated_at"] if sub else None,
            "expires_at": sub["expires_at"] if sub else None,
            "revoked_at": sub["revoked_at"] if sub else None}


# ---------------------------------------------------------------- send
@router.post("/send")
def send(body: SendIn, request: Request, p: Principal = Depends(require("premium:send"))):
    email = normalize_email(body.email)
    plan = body.plan.strip().lower()
    if plan not in PLANS:
        raise ApiError(422, "INVALID_PLAN", "Plan tidak dikenal", details={"allowed": list(PLANS)})
    duration = body.duration_days or PLANS[plan]
    ratelimit.enforce(f"am:send:{p.user_id}:{email}", 5, 900, "RATE_LIMITED",
                      "Terlalu banyak Magic Link untuk email ini. Coba lagi 15 menit lagi.")
    s = get_settings()
    ttl = s.magic_link_ttl_seconds
    token = generate_token(32)
    with db.transaction() as conn:
        # Invalidate older pending links for the same customer.
        db.execute("""UPDATE magic_link_tokens SET used_at = now()
                      WHERE owner_id = %s AND lower(email) = %s AND used_at IS NULL""", (p.user_id, email), conn)
        row = db.fetchone(
            """INSERT INTO magic_link_tokens (owner_id, api_key_id, email, plan, duration_days, token_hash, expires_at)
               VALUES (%s, %s, %s, %s, %s, %s, now() + make_interval(secs => %s)) RETURNING id, expires_at""",
            (p.user_id, p.api_key["id"] if p.api_key else None, email, plan, duration, sha256_hex(token), ttl),
            conn)
    url = f"{s.base_url(request)}/api/am/verif?token={token}"
    subject, html, text = email_templates.magic_link(url, email, ttl // 60, plan, body.name)
    result = send_email(email, subject, html, text, "magic_link", p.user_id)
    db.execute("UPDATE magic_link_tokens SET email_status = %s WHERE id = %s",
               ("sent" if result.ok else "failed", row["id"]))
    audit("premium.link_sent" if result.ok else "premium.link_failed", actor_type=p.auth_type.replace("session", "user"),
          actor_id=p.actor_label, user_id=p.user_id, target_type="email", target_id=email,
          metadata={"plan": plan, "duration_days": duration, "email_ok": result.ok})
    if not result.ok:
        # Burn the token: it was never delivered.
        db.execute("UPDATE magic_link_tokens SET used_at = now() WHERE id = %s", (row["id"],))
        raise ApiError(502, "EMAIL_DELIVERY_FAILED",
                       "Magic Link gagal dikirim. Periksa konfigurasi Resend (RESEND_API_KEY, EMAIL_FROM, domain).",
                       details={"provider_error": (result.error or "")[:160]})
    webhooks.dispatch(p.user_id, "premium.link_sent", {"email": email, "plan": plan})
    return ok({"email": email, "plan": plan, "duration_days": duration, "expires_in": ttl,
               "email_id": result.provider_id}, "Magic Link sent successfully")


# ---------------------------------------------------------------- verify
def verify_token(token: str) -> dict:
    """Atomic one-time verification. Raises ApiError on invalid/expired/used tokens."""
    with db.transaction() as conn:
        tok = db.fetchone("SELECT * FROM magic_link_tokens WHERE token_hash = %s FOR UPDATE",
                          (sha256_hex(token),), conn)
        if not tok:
            raise ApiError(400, "INVALID_TOKEN", "Magic Link tidak valid")
        if tok["used_at"] is not None:
            raise ApiError(409, "TOKEN_ALREADY_USED", "Magic Link sudah pernah digunakan")
        if tok["expires_at"] <= dt.datetime.now(dt.timezone.utc):
            raise ApiError(410, "TOKEN_EXPIRED", "Magic Link sudah kedaluwarsa. Minta tautan baru.")
        db.execute("UPDATE magic_link_tokens SET used_at = now() WHERE id = %s", (tok["id"],), conn)
        old = db.fetchone("""SELECT * FROM premium_subscriptions WHERE owner_id = %s AND lower(email) = lower(%s)
                             FOR UPDATE""", (tok["owner_id"], tok["email"]), conn)
        sub = db.fetchone(
            """INSERT INTO premium_subscriptions (owner_id, email, plan, status, activated_at, expires_at)
               VALUES (%(o)s, %(e)s, %(p)s, 'active', now(), now() + make_interval(days => %(d)s))
               ON CONFLICT (owner_id, lower(email)) DO UPDATE SET
                   plan = EXCLUDED.plan, status = 'active', activated_at = now(),
                   expires_at = CASE WHEN premium_subscriptions.status = 'active'
                                      AND premium_subscriptions.expires_at > now()
                                     THEN premium_subscriptions.expires_at + make_interval(days => %(d)s)
                                     ELSE now() + make_interval(days => %(d)s) END,
                   revoked_at = NULL, revoked_by = NULL, revoke_reason = NULL
               RETURNING *""",
            {"o": tok["owner_id"], "e": tok["email"], "p": tok["plan"], "d": tok["duration_days"]}, conn)
        db.execute(
            """INSERT INTO premium_renewal_logs (subscription_id, owner_id, action, duration_days, old_expires_at,
                                                 new_expires_at, actor_type, actor_id)
               VALUES (%s, %s, 'activate', %s, %s, %s, 'magic_link', %s)""",
            (sub["id"], tok["owner_id"], tok["duration_days"], old["expires_at"] if old else None,
             sub["expires_at"], str(tok["id"])), conn)
        audit("premium.activated", actor_type="system", actor_id=f"magic_link:{tok['id']}",
              user_id=str(tok["owner_id"]), target_type="email", target_id=tok["email"],
              metadata={"plan": tok["plan"], "expires_at": sub["expires_at"].isoformat()}, conn=conn)
        notify(str(tok["owner_id"]), "Premium diaktifkan", f"{tok['email']} berhasil memverifikasi Magic Link.",
               "success", conn=conn)
    subject, html, text = email_templates.premium_activated(sub["email"], _fmt(sub["expires_at"]), sub["plan"])
    send_email(sub["email"], subject, html, text, "premium_activated", str(tok["owner_id"]))
    webhooks.dispatch(str(tok["owner_id"]), "premium.activated",
                      {"email": sub["email"], "plan": sub["plan"], "expires_at": sub["expires_at"]})
    return sub


def _page(title: str, heading: str, body_html: str, ok_state: bool | None) -> HTMLResponse:
    color = {True: "#FFD600", False: "#FF6B6B", None: "#FFE766"}[ok_state]
    html = f"""<!doctype html><html lang="id"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex">
<title>{escape(title)} — AYAKA API</title><link rel="stylesheet" href="/css/style.css"></head>
<body class="verify-page"><main class="verify-wrap">
<a class="logo" href="/"><span class="logo-mark">AYAKA</span><span class="logo-text">API</span></a>
<section class="card verify-card" style="--accent:{color}">
<div class="verify-badge">{escape(heading)}</div>{body_html}</section>
<p class="powered">Powered by <strong>AYAKA Sync</strong> · Owner: OLPI STORE</p></main></body></html>"""
    return HTMLResponse(html, status_code=200 if ok_state is not False else 400)


@router.get("/verif", response_class=HTMLResponse)
def verif_page(token: str = Query("", max_length=200)):
    """Shows a confirmation page. The token is consumed only on POST, so email
    link-scanners that pre-fetch URLs cannot burn the one-time token."""
    if len(token) < 20:
        return _page("Tautan tidak valid", "TAUTAN TIDAK VALID",
                     "<h1>Magic Link tidak valid</h1><p>Tautan rusak atau tidak lengkap.</p>", False)
    tok = db.fetchone("SELECT email, plan, duration_days, expires_at, used_at FROM magic_link_tokens WHERE token_hash=%s",
                      (sha256_hex(token),))
    if not tok:
        return _page("Tautan tidak valid", "TAUTAN TIDAK VALID", "<h1>Magic Link tidak valid</h1>", False)
    if tok["used_at"]:
        return _page("Sudah digunakan", "SUDAH DIGUNAKAN",
                     "<h1>Magic Link sudah digunakan</h1><p>Tautan hanya berlaku satu kali.</p>", False)
    if tok["expires_at"] <= dt.datetime.now(dt.timezone.utc):
        return _page("Kedaluwarsa", "KEDALUWARSA",
                     "<h1>Magic Link kedaluwarsa</h1><p>Silakan minta tautan baru dari aplikasi Anda.</p>", False)
    body = f"""<h1>Aktifkan Premium</h1>
<p>Email: <strong>{escape(tok['email'])}</strong><br>Paket: <strong>{escape(tok['plan'].upper())}</strong>
 · Durasi: <strong>{tok['duration_days']} hari</strong></p>
<form method="post" action="/api/am/verif"><input type="hidden" name="token" value="{escape(token, quote=True)}">
<button class="btn btn-primary btn-lg" type="submit">Verify Account &rarr;</button></form>
<p class="muted small">Tautan sekali pakai · berlaku hingga {_fmt(tok['expires_at'])}</p>"""
    return _page("Verifikasi Premium", "VERIFIKASI", body, None)


@router.post("/verif")
async def verif(request: Request):
    ctype = request.headers.get("content-type", "")
    is_form = ctype.startswith("application/x-www-form-urlencoded") or ctype.startswith("multipart/form-data")
    if is_form:
        form = await request.form()
        token = str(form.get("token") or "")
    else:
        try:
            token = str((await request.json()).get("token") or "")
        except Exception:
            token = ""
    if not 20 <= len(token) <= 200:
        if is_form:
            return _page("Tautan tidak valid", "GAGAL", "<h1>Token tidak valid</h1>", False)
        raise ApiError(422, "INVALID_TOKEN", "Field token wajib diisi")
    from starlette.concurrency import run_in_threadpool
    try:
        sub = await run_in_threadpool(verify_token, token)
    except ApiError as exc:
        if is_form:
            return _page("Verifikasi gagal", "GAGAL", f"<h1>{escape(exc.message)}</h1>"
                         "<p>Minta Magic Link baru dari aplikasi yang Anda gunakan.</p>", False)
        raise
    if is_form:
        return _page("Premium aktif", "BERHASIL ✓",
                     f"<h1>Premium aktif!</h1><p><strong>{escape(sub['email'])}</strong> kini Premium hingga "
                     f"<strong>{_fmt(sub['expires_at'])}</strong>.</p><p class='muted'>Anda dapat menutup halaman ini.</p>",
                     True)
    return ok(_sub_payload(sub["email"], sub), "Premium activated")


# ---------------------------------------------------------------- status
@router.get("/status")
def status(email: str = Query(..., max_length=254), p: Principal = Depends(require("premium:status"))):
    email = normalize_email(email)
    sub = db.fetchone("SELECT * FROM premium_subscriptions WHERE owner_id = %s AND lower(email) = %s",
                      (p.user_id, email))
    return ok(_sub_payload(email, sub))


# ---------------------------------------------------------------- renew
def renew_subscription(owner_id: str, email: str, days: int, actor_type: str, actor_id: str) -> dict:
    with db.transaction() as conn:
        old = db.fetchone("""SELECT * FROM premium_subscriptions WHERE owner_id=%s AND lower(email)=%s
                             FOR UPDATE""", (owner_id, email), conn)
        if not old:
            raise ApiError(404, "SUBSCRIPTION_NOT_FOUND", "Belum ada Premium untuk email ini. Kirim Magic Link dulu.")
        sub = db.fetchone(
            """UPDATE premium_subscriptions
                  SET expires_at = GREATEST(expires_at, now()) + make_interval(days => %s),
                      status = 'active', revoked_at = NULL, revoked_by = NULL, revoke_reason = NULL
                WHERE id = %s RETURNING *""", (days, old["id"]), conn)
        db.execute(
            """INSERT INTO premium_renewal_logs (subscription_id, owner_id, action, duration_days, old_expires_at,
                                                 new_expires_at, actor_type, actor_id)
               VALUES (%s, %s, 'renew', %s, %s, %s, %s, %s)""",
            (sub["id"], owner_id, days, old["expires_at"], sub["expires_at"], actor_type, actor_id), conn)
        audit("premium.renewed", actor_type="admin" if actor_type == "admin" else
              ("api_key" if actor_type == "api_key" else "user"), actor_id=actor_id, user_id=owner_id,
              target_type="email", target_id=email, metadata={"days": days}, conn=conn)
    subject, html, text = email_templates.premium_renewed(email, _fmt(sub["expires_at"]), days)
    send_email(email, subject, html, text, "premium_renewed", owner_id)
    webhooks.dispatch(owner_id, "premium.renewed", {"email": email, "expires_at": sub["expires_at"], "days": days})
    return sub


@router.post("/renew")
def renew(body: RenewIn, p: Principal = Depends(require("premium:renew"))):
    email = normalize_email(body.email)
    sub = renew_subscription(p.user_id, email, body.duration_days,
                             "api_key" if p.api_key else "session", p.actor_label)
    data = _sub_payload(email, sub)
    data["renewed_days"] = body.duration_days
    return ok(data, "Premium renewed successfully")


# ---------------------------------------------------------------- revoke
def revoke_subscription(owner_id: str, email: str, reason: str | None, actor_type: str, actor_id: str) -> dict:
    with db.transaction() as conn:
        old = db.fetchone("""SELECT * FROM premium_subscriptions WHERE owner_id=%s AND lower(email)=%s
                             FOR UPDATE""", (owner_id, email), conn)
        if not old:
            raise ApiError(404, "SUBSCRIPTION_NOT_FOUND", "Premium untuk email ini tidak ditemukan")
        if old["status"] == "revoked":
            raise ApiError(409, "ALREADY_REVOKED", "Premium sudah dicabut sebelumnya")
        sub = db.fetchone(
            """UPDATE premium_subscriptions SET status='revoked', revoked_at=now(), revoked_by=%s, revoke_reason=%s
                WHERE id=%s RETURNING *""", (actor_id[:80], reason, old["id"]), conn)
        db.execute(
            """INSERT INTO premium_renewal_logs (subscription_id, owner_id, action, old_expires_at, new_expires_at,
                                                 actor_type, actor_id)
               VALUES (%s, %s, 'revoke', %s, %s, %s, %s)""",
            (sub["id"], owner_id, old["expires_at"], sub["expires_at"], actor_type, actor_id), conn)
        audit("premium.revoked", actor_type="admin" if actor_type == "admin" else
              ("api_key" if actor_type == "api_key" else "user"), actor_id=actor_id, user_id=owner_id,
              target_type="email", target_id=email, metadata={"reason": reason}, conn=conn)
    subject, html, text = email_templates.premium_revoked(email, reason)
    send_email(email, subject, html, text, "premium_revoked", owner_id)
    webhooks.dispatch(owner_id, "premium.revoked", {"email": email, "reason": reason, "by": actor_id})
    return sub


@router.post("/revoke")
def revoke(body: RevokeIn, p: Principal = Depends(require("premium:revoke"))):
    email = normalize_email(body.email)
    sub = revoke_subscription(p.user_id, email, body.reason, "api_key" if p.api_key else "session", p.actor_label)
    data = _sub_payload(email, sub)
    data["revoked_by"] = p.actor_label
    return ok(data, "Premium revoked successfully")


# ---------------------------------------------------------------- dashboard helpers
@premium_router.get("/subscriptions")
def subscriptions(p: Principal = Depends(require_session), q: str | None = Query(None, max_length=100),
                  page: int = Query(1, ge=1), per_page: int = Query(20, ge=1, le=100)):
    params: list = [p.user_id]
    where = "WHERE owner_id = %s"
    if q:
        where += " AND email ILIKE %s"
        params.append(f"%{q}%")
    total = db.scalar(f"SELECT count(*) FROM premium_subscriptions {where}", params)
    rows = db.fetchall(f"SELECT * FROM premium_subscriptions {where} ORDER BY updated_at DESC LIMIT %s OFFSET %s",
                       params + [per_page, (page - 1) * per_page])
    items = []
    for r in rows:
        d = _sub_payload(r["email"], r)
        d["id"] = r["id"]
        d["revoked_by"] = r["revoked_by"]
        items.append(d)
    return ok({"items": items, "total": total, "page": page, "per_page": per_page})


@premium_router.get("/history")
def history(p: Principal = Depends(require_session)):
    rows = db.fetchall(
        """SELECT l.action, l.duration_days, l.old_expires_at, l.new_expires_at, l.actor_type, l.actor_id,
                  l.created_at, s.email
             FROM premium_renewal_logs l JOIN premium_subscriptions s ON s.id = l.subscription_id
            WHERE l.owner_id = %s ORDER BY l.created_at DESC LIMIT 100""", (p.user_id,))
    links = db.fetchall(
        """SELECT email, plan, duration_days, email_status, created_at, expires_at, used_at
             FROM magic_link_tokens WHERE owner_id = %s ORDER BY created_at DESC LIMIT 50""", (p.user_id,))
    return ok({"events": rows, "links": links})
