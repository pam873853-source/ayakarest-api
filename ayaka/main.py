"""AYAKA API — FastAPI application factory. Powered by AYAKA Sync · Owner: OLPI STORE."""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import __version__
from .config import PUBLIC_DIR, get_settings
from .middleware import AyakaMiddleware
from .responses import ApiError, error_response
from .routers import admin, analytics, auth, keys, logs, magic_link, pages, system, user, webhooks

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("ayaka")


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(title="AYAKA API", version=__version__,
                  description="REST API Management Platform — Powered by AYAKA Sync · Owner: OLPI STORE",
                  docs_url="/api/swagger", redoc_url=None, openapi_url="/api/openapi.json")

    @app.exception_handler(ApiError)
    async def api_error_handler(request: Request, exc: ApiError):
        request.state.error_code = exc.code
        return error_response(exc.status, exc.code, exc.message, exc.details, exc.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        request.state.error_code = "VALIDATION_ERROR"
        details = [{"field": ".".join(str(x) for x in e.get("loc", [])[1:]), "message": e.get("msg")}
                   for e in exc.errors()]
        msg = details[0]["message"] if details else "Input tidak valid"
        if details and details[0]["field"]:
            msg = f"{details[0]['field']}: {msg}"
        return error_response(422, "VALIDATION_ERROR", msg, details)

    @app.exception_handler(StarletteHTTPException)
    async def http_handler(request: Request, exc: StarletteHTTPException):
        path = request.url.path
        if exc.status_code == 404 and not path.startswith("/api"):
            return FileResponse(PUBLIC_DIR / "404.html", status_code=404)
        codes = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED", 401: "UNAUTHORIZED", 403: "FORBIDDEN"}
        request.state.error_code = codes.get(exc.status_code, "HTTP_ERROR")
        return error_response(exc.status_code, codes.get(exc.status_code, "HTTP_ERROR"),
                              "Endpoint tidak ditemukan" if exc.status_code == 404 else str(exc.detail))

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        log.exception("unhandled error on %s", request.url.path)
        request.state.error_code = "INTERNAL_ERROR"
        return error_response(500, "INTERNAL_ERROR", "Terjadi kesalahan pada server",
                              {"request_id": getattr(request.state, "request_id", None)})

    app.add_middleware(AyakaMiddleware)
    app.add_middleware(
        CORSMiddleware, allow_origins=s.cors_origins or ["*"], allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-API-Key"],
        expose_headers=["X-Request-ID", "X-RateLimit-Limit", "X-RateLimit-Remaining", "Retry-After"],
        max_age=600)

    for r in (system.router, auth.router, user.router, keys.router, analytics.router, logs.router,
              magic_link.router, magic_link.premium_router, webhooks.router, admin.router):
        app.include_router(r)

    @app.api_route("/api/{rest:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"], include_in_schema=False)
    async def api_404(rest: str, request: Request):
        request.state.error_code = "NOT_FOUND"
        return error_response(404, "NOT_FOUND", "Endpoint tidak ditemukan")

    # Static assets (Vercel CDN serves /public in production; this mount is for local dev / fallback).
    for sub in ("css", "js", "assets"):
        if (PUBLIC_DIR / sub).is_dir():
            app.mount(f"/{sub}", StaticFiles(directory=PUBLIC_DIR / sub), name=sub)

    @app.get("/", include_in_schema=False)
    async def index():
        return FileResponse(PUBLIC_DIR / "index.html")

    app.include_router(pages.router)
    return app


app = create_app()
