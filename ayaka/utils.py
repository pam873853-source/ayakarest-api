from __future__ import annotations

from fastapi import Request

from .security import mask_ip


def client_ip(request: Request) -> str | None:
    # Vercel sets x-forwarded-for / x-real-ip; first hop is the client.
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    xri = request.headers.get("x-real-ip")
    if xri:
        return xri.strip()
    return request.client.host if request.client else None


def masked_ip(request: Request) -> str | None:
    return mask_ip(client_ip(request))


def user_agent(request: Request) -> str:
    return (request.headers.get("user-agent") or "")[:300]


def public_user(u: dict) -> dict:
    return {
        "id": u["id"], "username": u["username"], "full_name": u["full_name"], "email": u["email"],
        "status": u["status"], "monthly_quota": u.get("monthly_quota"),
        "created_at": u.get("created_at"), "last_login_at": u.get("last_login_at"),
    }
