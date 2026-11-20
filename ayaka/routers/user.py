"""User profile, password, sessions, usage."""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from .. import db
from ..deps import Principal, require, require_session
from ..responses import ApiError, ok
from ..security import hash_password, password_problems, verify_password
from ..services import email_templates
from ..services.activity import audit, notify
from ..services.resend_client import send_email
from ..utils import masked_ip, public_user

router = APIRouter(prefix="/api/user", tags=["user"])


class ProfileIn(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=120)


class ChangePasswordIn(BaseModel):
    current_password: str = Field(max_length=128)
    new_password: str = Field(max_length=128)
    confirm_password: str = Field(max_length=128)


@router.get("/profile")
def profile(p: Principal = Depends(require("profile:read"))):
    u = db.fetchone("SELECT * FROM users WHERE id = %s", (p.user_id,))
    data = public_user(u)
    data["auth_type"] = p.auth_type
    if p.api_key:
        data["api_key"] = {"id": p.api_key["id"], "name": p.api_key["name"],
                           "permissions": p.api_key["permissions"]}
    data["is_admin"] = p.is_admin
    return ok(data)


@router.patch("/profile")
def update_profile(body: ProfileIn, request: Request, p: Principal = Depends(require_session)):
    u = db.fetchone("UPDATE users SET full_name = COALESCE(%s, full_name) WHERE id = %s RETURNING *",
                    (body.full_name.strip() if body.full_name else None, p.user_id))
    audit("user.profile_updated", actor_type="user", actor_id=p.user_id, user_id=p.user_id,
          ip_masked=masked_ip(request))
    return ok(public_user(u), "Profil diperbarui")


@router.post("/change-password")
def change_password(body: ChangePasswordIn, request: Request, p: Principal = Depends(require_session)):
    u = db.fetchone("SELECT * FROM users WHERE id = %s", (p.user_id,))
    if not verify_password(u["password_hash"], body.current_password):
        raise ApiError(401, "INVALID_CREDENTIALS", "Password saat ini salah")
    problems = password_problems(body.new_password)
    if problems:
        raise ApiError(422, "WEAK_PASSWORD", problems[0], details={"problems": problems})
    if body.new_password != body.confirm_password:
        raise ApiError(422, "PASSWORD_MISMATCH", "Konfirmasi password tidak sama")
    with db.transaction() as conn:
        db.execute("UPDATE users SET password_hash = %s, password_changed_at = now() WHERE id = %s",
                   (hash_password(body.new_password), p.user_id), conn)
        # Sign out every other session.
        db.execute("""UPDATE user_sessions SET revoked_at = now()
                      WHERE user_id = %s AND id <> %s AND revoked_at IS NULL""",
                   (p.user_id, p.session["session_id"]), conn)
        audit("user.password_changed", actor_type="user", actor_id=p.user_id, user_id=p.user_id,
              ip_masked=masked_ip(request), conn=conn)
        notify(p.user_id, "Password diubah", "Sesi lain telah dikeluarkan.", "security", conn=conn)
    subject, html, text = email_templates.security_notice(
        u["full_name"], "Password diubah", dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M"),
        masked_ip(request))
    send_email(u["email"], subject, html, text, "security_notice", p.user_id)
    return ok({}, "Password berhasil diubah")


@router.get("/sessions")
def sessions(p: Principal = Depends(require_session)):
    rows = db.fetchall(
        """SELECT id, remember_me, ip_masked, user_agent, created_at, last_seen_at, expires_at
             FROM user_sessions WHERE user_id = %s AND revoked_at IS NULL AND expires_at > now()
            ORDER BY last_seen_at DESC""", (p.user_id,))
    for r in rows:
        r["current"] = str(r["id"]) == str(p.session["session_id"])
    return ok({"items": rows})


@router.delete("/sessions/{session_id}")
def revoke_session(session_id: str, request: Request, p: Principal = Depends(require_session)):
    try:
        n = db.execute("UPDATE user_sessions SET revoked_at = now() WHERE id = %s AND user_id = %s AND revoked_at IS NULL",
                       (session_id, p.user_id))
    except Exception:
        n = 0
    if not n:
        raise ApiError(404, "SESSION_NOT_FOUND", "Sesi tidak ditemukan")
    audit("user.session_revoked", actor_type="user", actor_id=p.user_id, user_id=p.user_id,
          target_type="session", target_id=session_id, ip_masked=masked_ip(request))
    return ok({}, "Sesi dikeluarkan")


@router.get("/usage")
def usage(p: Principal = Depends(require("analytics:read"))):
    u = db.fetchone("SELECT monthly_quota FROM users WHERE id = %s", (p.user_id,))
    used = db.scalar(
        """SELECT count(*) FROM api_request_logs WHERE user_id = %s AND auth_type = 'api_key'
              AND created_at >= date_trunc('month', now())""", (p.user_id,))
    daily = db.fetchall(
        """SELECT d::date AS day, count(l.id) AS requests
             FROM generate_series(date_trunc('day', now()) - interval '29 days', date_trunc('day', now()), interval '1 day') d
        LEFT JOIN api_request_logs l ON l.user_id = %s AND l.auth_type = 'api_key'
                                     AND l.created_at >= d AND l.created_at < d + interval '1 day'
         GROUP BY d ORDER BY d""", (p.user_id,))
    return ok({"monthly_quota": u["monthly_quota"], "used_this_month": used,
               "remaining": max(0, u["monthly_quota"] - used), "daily": daily})
