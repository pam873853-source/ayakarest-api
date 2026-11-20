"""Register, login, logout, session info, forgot/reset password."""
from __future__ import annotations

import datetime as dt
import secrets

from email_validator import EmailNotValidError, validate_email
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .. import db
from ..config import get_settings
from ..deps import load_session, require_session
from ..responses import ApiError, ok
from ..security import (generate_token, hash_password, password_needs_rehash, password_problems,
                        sha256_hex, verify_password)
from ..services import email_templates, ratelimit, settings_store
from ..services.activity import audit, notify
from ..services.resend_client import send_email
from ..utils import masked_ip, public_user, user_agent

router = APIRouter(prefix="/api/auth", tags=["auth"])

MAX_FAILED = 5
LOCK_MINUTES = 15
RESET_TTL_MIN = 30


def normalize_email(email: str) -> str:
    try:
        return validate_email(email.strip(), check_deliverability=False).normalized.lower()
    except EmailNotValidError:
        raise ApiError(422, "INVALID_EMAIL", "Format email tidak valid")


class RegisterIn(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    full_name: str = Field(min_length=2, max_length=120)
    email: str = Field(max_length=254)
    password: str = Field(max_length=128)
    confirm_password: str = Field(max_length=128)


class LoginIn(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=128)
    remember_me: bool = False


class ForgotIn(BaseModel):
    email: str = Field(max_length=254)


class ResetIn(BaseModel):
    token: str = Field(min_length=20, max_length=200)
    password: str = Field(max_length=128)
    confirm_password: str = Field(max_length=128)


def create_session(response: JSONResponse, request: Request, user_id: str, remember: bool) -> str:
    s = get_settings()
    token = generate_token(32)
    csrf = secrets.token_urlsafe(24)
    lifetime = dt.timedelta(days=s.remember_days) if remember else dt.timedelta(hours=s.session_hours)
    db.execute(
        """INSERT INTO user_sessions (user_id, token_hash, csrf_token, remember_me, ip_masked, user_agent, expires_at)
           VALUES (%s, %s, %s, %s, %s, %s, now() + %s)""",
        (user_id, sha256_hex(token), csrf, remember, masked_ip(request), user_agent(request), lifetime))
    max_age = int(lifetime.total_seconds()) if remember else None
    response.set_cookie(s.session_cookie_name, token, max_age=max_age, httponly=True,
                        secure=s.cookie_secure, samesite="lax", path="/")
    response.set_cookie(s.csrf_cookie_name, csrf, max_age=max_age, httponly=False,
                        secure=s.cookie_secure, samesite="strict", path="/")
    return csrf


def clear_session_cookies(response: JSONResponse) -> None:
    s = get_settings()
    for name in (s.session_cookie_name, s.csrf_cookie_name):
        response.delete_cookie(name, path="/", secure=s.cookie_secure,
                               httponly=name == s.session_cookie_name, samesite="lax")


@router.post("/register")
def register(body: RegisterIn, request: Request):
    if not (settings_store.get("registration") or {}).get("open", True):
        raise ApiError(403, "REGISTRATION_CLOSED", "Pendaftaran akun baru sedang ditutup")
    ratelimit.enforce(f"register:{masked_ip(request)}", 10, 3600)
    username = body.username.strip()
    if not username.replace("_", "").isalnum() or not username.isascii():
        raise ApiError(422, "INVALID_USERNAME", "Username hanya boleh huruf, angka, dan underscore (3–32)")
    email = normalize_email(body.email)
    problems = password_problems(body.password)
    if problems:
        raise ApiError(422, "WEAK_PASSWORD", problems[0], details={"problems": problems})
    if body.password != body.confirm_password:
        raise ApiError(422, "PASSWORD_MISMATCH", "Konfirmasi password tidak sama")
    if db.fetchone("SELECT 1 FROM users WHERE lower(email) = %s", (email,)):
        raise ApiError(409, "EMAIL_EXISTS", "Email sudah terdaftar. Silakan login.")
    if db.fetchone("SELECT 1 FROM users WHERE lower(username) = lower(%s)", (username,)):
        raise ApiError(409, "USERNAME_EXISTS", "Username sudah digunakan")
    quota = int((settings_store.get("defaults") or {}).get("monthly_quota", 10000))
    try:
        user = db.fetchone(
            """INSERT INTO users (username, full_name, email, password_hash, monthly_quota, password_changed_at)
               VALUES (%s, %s, %s, %s, %s, now()) RETURNING *""",
            (username, body.full_name.strip(), email, hash_password(body.password), quota))
    except Exception as exc:  # race on unique index
        if "unique" in str(exc).lower():
            raise ApiError(409, "EMAIL_EXISTS", "Email atau username sudah terdaftar")
        raise
    uid = str(user["id"])
    audit("user.register", actor_type="user", actor_id=uid, user_id=uid, target_type="user",
          target_id=uid, ip_masked=masked_ip(request))
    notify(uid, "Selamat datang di AYAKA API", "Buat API Key pertama Anda di menu API Key Manager.", "success")
    request.state.user_id = uid
    resp = ok({"user": public_user(user)}, "Registrasi berhasil", 201)
    create_session(resp, request, uid, remember=False)
    return resp


@router.post("/login")
def login(body: LoginIn, request: Request):
    ip = masked_ip(request)
    ratelimit.enforce(f"login:ip:{ip}", 30, 900, "TOO_MANY_ATTEMPTS",
                      "Terlalu banyak percobaan login dari jaringan ini. Coba lagi 15 menit lagi.")
    email = body.email.strip().lower()
    ratelimit.enforce(f"login:email:{email}", 15, 900, "TOO_MANY_ATTEMPTS",
                      "Terlalu banyak percobaan login untuk akun ini. Coba lagi 15 menit lagi.")
    user = db.fetchone("SELECT * FROM users WHERE lower(email) = %s", (email,))
    now = dt.datetime.now(dt.timezone.utc)
    if user and user["locked_until"] and user["locked_until"] > now:
        raise ApiError(429, "ACCOUNT_LOCKED", "Akun dikunci sementara karena terlalu banyak login gagal",
                       details={"locked_until": user["locked_until"]})
    if not verify_password(user["password_hash"] if user else None, body.password):
        if user:
            row = db.fetchone(
                """UPDATE users SET failed_login_count = failed_login_count + 1,
                          locked_until = CASE WHEN failed_login_count + 1 >= %s
                                              THEN now() + make_interval(mins => %s) ELSE locked_until END
                    WHERE id = %s RETURNING failed_login_count, locked_until""",
                (MAX_FAILED, LOCK_MINUTES, user["id"]))
            audit("auth.login_failed", actor_type="user", actor_id=str(user["id"]), user_id=str(user["id"]),
                  ip_masked=ip)
            if row["failed_login_count"] >= MAX_FAILED:
                db.execute("UPDATE users SET failed_login_count = 0 WHERE id = %s", (user["id"],))
                notify(str(user["id"]), "Akun dikunci sementara",
                       "Terdeteksi 5 kali login gagal. Akun dikunci 15 menit.", "security")
        raise ApiError(401, "INVALID_CREDENTIALS", "Email atau password salah")
    if user["status"] != "active":
        raise ApiError(403, "ACCOUNT_SUSPENDED", "Akun Anda sedang ditangguhkan. Hubungi administrator.")
    uid = str(user["id"])
    new_hash = hash_password(body.password) if password_needs_rehash(user["password_hash"]) else None
    db.execute(
        """UPDATE users SET failed_login_count = 0, locked_until = NULL, last_login_at = now(),
                  password_hash = COALESCE(%s, password_hash) WHERE id = %s""", (new_hash, uid))
    db.execute("DELETE FROM user_sessions WHERE user_id = %s AND (expires_at < now() OR revoked_at IS NOT NULL)", (uid,))
    audit("auth.login", actor_type="user", actor_id=uid, user_id=uid, ip_masked=ip,
          metadata={"remember_me": body.remember_me})
    request.state.user_id = uid
    request.state.auth_type = "session"
    is_admin = bool(db.fetchone("SELECT 1 FROM admin_users WHERE user_id = %s", (uid,)))
    resp = ok({"user": public_user(user), "is_admin": is_admin,
               "redirect": "/admin" if is_admin else "/dashboard"}, "Login berhasil")
    create_session(resp, request, uid, body.remember_me)
    return resp


@router.post("/logout")
def logout(request: Request):
    row = load_session(request)
    if row:
        # CSRF still required to prevent forced logout from other sites.
        require_session(request)
        db.execute("UPDATE user_sessions SET revoked_at = now() WHERE id = %s", (row["session_id"],))
        audit("auth.logout", actor_type="user", actor_id=str(row["id"]), user_id=str(row["id"]),
              ip_masked=masked_ip(request))
    resp = ok({"redirect": "/login"}, "Logout berhasil")
    clear_session_cookies(resp)
    return resp


@router.get("/me")
def me(request: Request):
    row = load_session(request)
    if not row:
        raise ApiError(401, "UNAUTHORIZED", "Belum login")
    return ok({"user": public_user(row), "is_admin": row.get("admin_role") is not None,
               "admin_role": row.get("admin_role"), "csrf_token": row["csrf_token"],
               "session_expires_at": row["expires_at"], "remember_me": row["remember_me"]})


@router.post("/forgot-password")
def forgot_password(body: ForgotIn, request: Request):
    ratelimit.enforce(f"forgot:ip:{masked_ip(request)}", 10, 3600)
    generic = ok({}, "Jika email terdaftar, tautan reset password telah dikirim.")
    try:
        email = normalize_email(body.email)
    except ApiError:
        return generic
    allowed, _, _ = ratelimit.hit(f"forgot:email:{email}", 3, 3600)
    user = db.fetchone("SELECT * FROM users WHERE lower(email) = %s AND status = 'active'", (email,))
    if not user or not allowed:
        return generic
    token = generate_token(32)
    db.execute("UPDATE password_reset_tokens SET used_at = now() WHERE user_id = %s AND used_at IS NULL", (user["id"],))
    db.execute("""INSERT INTO password_reset_tokens (user_id, token_hash, expires_at)
                  VALUES (%s, %s, now() + make_interval(mins => %s))""",
               (user["id"], sha256_hex(token), RESET_TTL_MIN))
    url = f"{get_settings().base_url(request)}/reset-password?token={token}"
    subject, html, text = email_templates.reset_password(user["full_name"], url, RESET_TTL_MIN)
    result = send_email(user["email"], subject, html, text, "reset_password", str(user["id"]))
    audit("auth.forgot_password", actor_type="user", actor_id=str(user["id"]), user_id=str(user["id"]),
          ip_masked=masked_ip(request), metadata={"email_sent": result.ok})
    return generic


@router.post("/reset-password")
def reset_password(body: ResetIn, request: Request):
    ratelimit.enforce(f"reset:ip:{masked_ip(request)}", 20, 3600)
    problems = password_problems(body.password)
    if problems:
        raise ApiError(422, "WEAK_PASSWORD", problems[0], details={"problems": problems})
    if body.password != body.confirm_password:
        raise ApiError(422, "PASSWORD_MISMATCH", "Konfirmasi password tidak sama")
    with db.transaction() as conn:
        tok = db.fetchone("SELECT * FROM password_reset_tokens WHERE token_hash = %s FOR UPDATE",
                          (sha256_hex(body.token),), conn)
        if not tok or tok["used_at"] is not None:
            raise ApiError(400, "INVALID_TOKEN", "Tautan reset tidak valid atau sudah digunakan")
        if tok["expires_at"] <= dt.datetime.now(dt.timezone.utc):
            raise ApiError(400, "TOKEN_EXPIRED", "Tautan reset sudah kedaluwarsa")
        db.execute("UPDATE password_reset_tokens SET used_at = now() WHERE id = %s", (tok["id"],), conn)
        user = db.fetchone(
            """UPDATE users SET password_hash = %s, password_changed_at = now(), failed_login_count = 0,
                      locked_until = NULL WHERE id = %s RETURNING *""",
            (hash_password(body.password), tok["user_id"]), conn)
        db.execute("UPDATE user_sessions SET revoked_at = now() WHERE user_id = %s AND revoked_at IS NULL",
                   (tok["user_id"],), conn)
    uid = str(user["id"])
    audit("auth.password_reset", actor_type="user", actor_id=uid, user_id=uid, ip_masked=masked_ip(request))
    notify(uid, "Password direset", "Semua sesi lama telah dikeluarkan.", "security")
    subject, html, text = email_templates.security_notice(
        user["full_name"], "Password direset", dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M"),
        masked_ip(request))
    send_email(user["email"], subject, html, text, "security_notice", uid)
    return ok({"redirect": "/login"}, "Password berhasil direset. Silakan login.")
