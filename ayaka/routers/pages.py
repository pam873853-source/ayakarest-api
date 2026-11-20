"""Server-guarded HTML pages (dashboard, admin) + local static fallback.

/dashboard and /admin are rendered by the backend so authentication is checked
server-side before any HTML is sent. Public pages are static files in /public
(served by Vercel's CDN in production, and by this router locally)."""
from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from starlette.concurrency import run_in_threadpool

from ..config import PUBLIC_DIR, TEMPLATES_DIR
from ..deps import load_session
from ..services import settings_store

router = APIRouter(include_in_schema=False)
PUBLIC_PAGES = {"index", "login", "register", "documentation", "maintenance", "forgot-password",
                "reset-password", "status", "404"}


def _template(name: str) -> HTMLResponse:
    html = (TEMPLATES_DIR / name).read_text(encoding="utf-8")
    return HTMLResponse(html, headers={"Cache-Control": "no-store"})


async def _guard(request: Request, admin: bool):
    row = await run_in_threadpool(load_session, request)
    if not row:
        nxt = quote(request.url.path)
        return RedirectResponse(f"/login?next={nxt}", status_code=302)
    is_admin = row.get("admin_role") is not None
    if admin and not is_admin:
        return RedirectResponse("/dashboard?denied=admin", status_code=302)
    if not is_admin:
        m = await run_in_threadpool(settings_store.maintenance_state)
        if m.get("active"):
            return RedirectResponse("/maintenance", status_code=302)
    return None


@router.get("/dashboard")
async def dashboard(request: Request):
    return await _guard(request, admin=False) or _template("dashboard.html")


@router.get("/admin")
async def admin(request: Request):
    return await _guard(request, admin=True) or _template("admin.html")


@router.get("/login")
@router.get("/register")
async def auth_pages(request: Request):
    # Already logged in → go straight to the dashboard.
    row = await run_in_threadpool(load_session, request)
    if row:
        return RedirectResponse("/admin" if row.get("admin_role") else "/dashboard", status_code=302)
    return FileResponse(PUBLIC_DIR / f"{request.url.path.strip('/')}.html")


@router.get("/{page}")
async def public_page(page: str):
    name = page[:-5] if page.endswith(".html") else page
    if name in PUBLIC_PAGES and (PUBLIC_DIR / f"{name}.html").is_file():
        return FileResponse(PUBLIC_DIR / f"{name}.html")
    target = (PUBLIC_DIR / page).resolve()
    if target.is_file() and PUBLIC_DIR.resolve() in target.parents:
        return FileResponse(target)
    return FileResponse(PUBLIC_DIR / "404.html", status_code=404)
