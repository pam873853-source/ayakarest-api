from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from .. import db
from ..config import WEBHOOK_EVENTS
from ..deps import Principal, require_session
from ..responses import ApiError, ok
from ..security import encrypt_secret, generate_token
from ..services import webhooks as wh
from ..services.activity import audit
from ..utils import masked_ip

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])
COLS = "id, url, events, is_active, last_status_code, last_delivery_at, last_error, failure_count, created_at, updated_at"
MAX_HOOKS = 10


class HookIn(BaseModel):
    url: str = Field(min_length=10, max_length=500)
    events: list[str] = Field(min_length=1)
    is_active: bool = True


class HookUpdate(BaseModel):
    url: str | None = Field(default=None, min_length=10, max_length=500)
    events: list[str] | None = None
    is_active: bool | None = None


def _events(ev: list[str]) -> list[str]:
    bad = [e for e in ev if e not in WEBHOOK_EVENTS]
    if bad:
        raise ApiError(422, "INVALID_EVENT", f"Event tidak dikenal: {', '.join(bad)}",
                       details={"allowed": WEBHOOK_EVENTS})
    return sorted(set(ev))


def _owned(hook_id: str, owner: str) -> dict:
    try:
        uuid.UUID(hook_id)
    except ValueError:
        raise ApiError(404, "WEBHOOK_NOT_FOUND", "Webhook tidak ditemukan")
    row = db.fetchone("SELECT * FROM webhook_configs WHERE id=%s AND owner_id=%s", (hook_id, owner))
    if not row:
        raise ApiError(404, "WEBHOOK_NOT_FOUND", "Webhook tidak ditemukan")
    return row


@router.get("")
def list_hooks(p: Principal = Depends(require_session)):
    rows = db.fetchall(f"SELECT {COLS} FROM webhook_configs WHERE owner_id=%s ORDER BY created_at DESC", (p.user_id,))
    return ok({"items": rows, "available_events": WEBHOOK_EVENTS})


@router.post("")
def create_hook(body: HookIn, request: Request, p: Principal = Depends(require_session)):
    err = wh.validate_url(body.url)
    if err:
        raise ApiError(422, "INVALID_WEBHOOK_URL", err)
    if db.scalar("SELECT count(*) FROM webhook_configs WHERE owner_id=%s", (p.user_id,)) >= MAX_HOOKS:
        raise ApiError(409, "WEBHOOK_LIMIT", f"Maksimal {MAX_HOOKS} webhook per akun")
    secret = "whsec_" + generate_token(24)
    row = db.fetchone(
        f"""INSERT INTO webhook_configs (owner_id, url, events, secret_encrypted, is_active)
            VALUES (%s,%s,%s,%s,%s) RETURNING {COLS}""",
        (p.user_id, body.url, _events(body.events), encrypt_secret(secret), body.is_active))
    audit("webhook.created", actor_type="user", actor_id=p.user_id, user_id=p.user_id, target_type="webhook",
          target_id=str(row["id"]), metadata={"url": body.url}, ip_masked=masked_ip(request))
    row["signing_secret"] = secret
    return ok(row, "Webhook dibuat. Simpan signing secret — hanya ditampilkan sekali.", 201)


@router.patch("/{hook_id}")
def update_hook(hook_id: str, body: HookUpdate, request: Request, p: Principal = Depends(require_session)):
    old = _owned(hook_id, p.user_id)
    if body.url:
        err = wh.validate_url(body.url)
        if err:
            raise ApiError(422, "INVALID_WEBHOOK_URL", err)
    row = db.fetchone(
        f"""UPDATE webhook_configs SET url=%s, events=%s, is_active=%s WHERE id=%s RETURNING {COLS}""",
        (body.url or old["url"], _events(body.events) if body.events is not None else old["events"],
         old["is_active"] if body.is_active is None else body.is_active, old["id"]))
    audit("webhook.updated", actor_type="user", actor_id=p.user_id, user_id=p.user_id, target_type="webhook",
          target_id=hook_id, ip_masked=masked_ip(request))
    return ok(row, "Webhook diperbarui")


@router.delete("/{hook_id}")
def delete_hook(hook_id: str, request: Request, p: Principal = Depends(require_session)):
    _owned(hook_id, p.user_id)
    db.execute("DELETE FROM webhook_configs WHERE id=%s AND owner_id=%s", (hook_id, p.user_id))
    audit("webhook.deleted", actor_type="user", actor_id=p.user_id, user_id=p.user_id, target_type="webhook",
          target_id=hook_id, ip_masked=masked_ip(request))
    return ok({}, "Webhook dihapus")


@router.post("/{hook_id}/test")
def test_hook(hook_id: str, p: Principal = Depends(require_session)):
    hook = _owned(hook_id, p.user_id)
    status, err = wh.deliver(hook, "webhook.test", {"message": "Test event dari AYAKA Sync"})
    return ok({"status_code": status, "error": err, "delivered": err is None},
              "Test webhook terkirim" if err is None else "Test webhook gagal")
