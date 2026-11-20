"""Central configuration. Every value comes from environment variables."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PUBLIC_DIR = PROJECT_ROOT / "public"
TEMPLATES_DIR = PROJECT_ROOT / "templates"

APP_NAME = "AYAKA API"
SYSTEM_NAME = "AYAKA Sync"
OWNER = "OLPI STORE"
ADMIN_NAME = "Ayaka Sync"
GITHUB_URL = "https://github.com/olpigiantara-design"
WHATSAPP_CHANNEL_URL = "https://whatsapp.com/channel/0029VbEbK4dHgZWWJmXFP52o"

# All permissions an API key can hold.
PERMISSIONS: dict[str, str] = {
    "profile:read": "Membaca profil akun pemilik API Key",
    "keys:read": "Membaca daftar & detail metadata API Key",
    "keys:revoke": "Mencabut (revoke) API Key milik akun sendiri",
    "analytics:read": "Membaca statistik penggunaan",
    "logs:read": "Membaca riwayat request",
    "premium:send": "Mengirim Magic Link Premium",
    "premium:status": "Memeriksa status Premium",
    "premium:renew": "Memperpanjang Premium",
    "premium:revoke": "Mencabut Premium",
}

WEBHOOK_EVENTS = [
    "key.created", "key.revoked", "key.regenerated",
    "premium.link_sent", "premium.activated", "premium.renewed", "premium.revoked",
]


def _bool(v: str | None, default: bool = False) -> bool:
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    database_url: str
    base_url_env: str
    resend_api_key: str
    email_from: str
    admin_email: str
    secret_key: str
    api_key_pepper: str
    session_secret: str
    environment: str
    cors_origins: list[str] = field(default_factory=list)
    max_body_bytes: int = 1_048_576
    magic_link_ttl_seconds: int = 900
    session_hours: int = 12
    remember_days: int = 30
    visitor_retention_days: int = 90
    log_retention_days: int = 90

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def cookie_secure(self) -> bool:
        # Secure cookies everywhere except explicit local development over http.
        return self.environment != "development"

    @property
    def session_cookie_name(self) -> str:
        return "__Host-ayaka_session" if self.cookie_secure else "ayaka_session"

    @property
    def csrf_cookie_name(self) -> str:
        return "__Host-ayaka_csrf" if self.cookie_secure else "ayaka_csrf"

    @property
    def email_configured(self) -> bool:
        return bool(self.resend_api_key and self.email_from)

    def base_url(self, request=None) -> str:
        """Single source of truth for BASE_URL."""
        if self.base_url_env:
            return self.base_url_env.rstrip("/")
        prod = os.getenv("VERCEL_PROJECT_PRODUCTION_URL")
        if prod:
            return f"https://{prod}".rstrip("/")
        vurl = os.getenv("VERCEL_URL")
        if vurl:
            return f"https://{vurl}".rstrip("/")
        if request is not None:
            return str(request.base_url).rstrip("/")
        return "http://localhost:8000"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    env = os.getenv("ENVIRONMENT", "production").strip().lower()
    secret = os.getenv("SECRET_KEY", "")
    pepper = os.getenv("API_KEY_PEPPER", "")
    session_secret = os.getenv("SESSION_SECRET", "")
    if env == "production":
        missing = [n for n, v in (("SECRET_KEY", secret), ("API_KEY_PEPPER", pepper),
                                  ("SESSION_SECRET", session_secret)) if len(v) < 32]
        if missing:
            raise RuntimeError(
                "Missing/too-short secrets (min 32 chars): " + ", ".join(missing))
    cors = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]
    return Settings(
        database_url=os.getenv("DATABASE_URL", ""),
        base_url_env=os.getenv("BASE_URL", "").strip(),
        resend_api_key=os.getenv("RESEND_API_KEY", "").strip(),
        email_from=os.getenv("EMAIL_FROM", "").strip(),
        admin_email=os.getenv("ADMIN_EMAIL", "olpieditz336@gmail.com").strip(),
        secret_key=secret or "dev-secret-key-change-me-dev-secret-key",
        api_key_pepper=pepper or "dev-pepper-change-me-dev-pepper-change-me",
        session_secret=session_secret or "dev-session-secret-change-me-dev-session",
        environment=env,
        cors_origins=cors,
        max_body_bytes=int(os.getenv("MAX_BODY_BYTES", "1048576")),
    )
