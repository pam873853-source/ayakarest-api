"""pytest fixtures. Requires a real PostgreSQL database (local Postgres or a Neon branch):

    export TEST_DATABASE_URL=postgresql://postgres:postgres@localhost/ayaka_test
    pytest -q

WARNING: the test database schema is dropped and recreated on every run.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TEST_DB = os.getenv("TEST_DATABASE_URL", "postgresql://postgres:postgres@localhost/ayaka_test")
os.environ.update({
    "DATABASE_URL": TEST_DB, "ENVIRONMENT": "development", "BASE_URL": "http://testserver",
    "RESEND_API_KEY": "re_test_dummy", "EMAIL_FROM": "AYAKA API <noreply@example.com>",
    "SECRET_KEY": "t" * 40, "API_KEY_PEPPER": "p" * 40, "SESSION_SECRET": "s" * 40,
})

import psycopg  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from ayaka import db  # noqa: E402
from ayaka.main import app  # noqa: E402
from ayaka.services import resend_client, settings_store  # noqa: E402


class FakeResp:
    def __init__(self, status=200, data=None):
        self.status_code = status
        self._d = data or {"id": "email_test_123"}

    def json(self):
        return self._d


@pytest.fixture(scope="session", autouse=True)
def schema():
    sql = (ROOT / "database" / "schema.sql").read_text()
    with psycopg.connect(TEST_DB, autocommit=True) as c:
        c.execute("DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;")
        c.execute(sql)
    yield
    db.close_pool()


@pytest.fixture(autouse=True)
def clean():
    with psycopg.connect(TEST_DB, autocommit=True) as c:
        c.execute("""TRUNCATE users, api_keys, api_request_logs, magic_link_tokens, premium_subscriptions,
                     premium_renewal_logs, admin_users, user_sessions, audit_logs, visitor_analytics,
                     webhook_configs, rate_limit_counters, password_reset_tokens, email_logs, notifications,
                     announcements CASCADE""")
        c.execute("""UPDATE system_settings SET value = '{"enabled": false, "message": "m", "start_at": null, "end_at": null}'
                     WHERE key = 'maintenance'""")
        c.execute("""UPDATE system_settings SET value = '{"open": true}' WHERE key = 'registration'""")
    settings_store.clear_cache()
    yield


@pytest.fixture
def outbox(monkeypatch):
    sent: list[dict] = []

    def fake_post(payload, api_key):
        sent.append(payload)
        return FakeResp()
    monkeypatch.setattr(resend_client, "_post", fake_post)
    return sent


def extract_token(html: str, param: str = "token") -> str:
    m = re.search(param + r"=([A-Za-z0-9_\-]+)", html)
    assert m, "token not found in email"
    return m.group(1)


class Client(TestClient):
    def csrf(self) -> dict:
        return {"X-CSRF-Token": self.cookies.get("ayaka_csrf", "")}

    def spost(self, url, **kw):
        return self.post(url, headers={**self.csrf(), **kw.pop("headers", {})}, **kw)

    def sdelete(self, url, **kw):
        return self.request("DELETE", url, headers={**self.csrf(), **kw.pop("headers", {})}, **kw)

    def sput(self, url, **kw):
        return self.put(url, headers={**self.csrf(), **kw.pop("headers", {})}, **kw)

    def spatch(self, url, **kw):
        return self.patch(url, headers={**self.csrf(), **kw.pop("headers", {})}, **kw)


def make_client() -> Client:
    return Client(app)


PASSWORD = "Rahasia123"


def register(client: Client, n: str = "alice") -> dict:
    r = client.post("/api/auth/register", json={
        "username": n, "full_name": n.title() + " Tester", "email": f"{n}@example.com",
        "password": PASSWORD, "confirm_password": PASSWORD})
    assert r.status_code == 201, r.text
    return r.json()["data"]["user"]


def make_key(client: Client, perms=None, **extra) -> dict:
    perms = perms or ["profile:read", "keys:read", "analytics:read", "logs:read", "premium:send",
                      "premium:status", "premium:renew", "premium:revoke"]
    r = client.spost("/api/keys/generate", json={"name": "Test Key", "permissions": perms, **extra})
    assert r.status_code == 201, r.text
    return r.json()["data"]


@pytest.fixture
def client():
    with make_client() as c:
        yield c


@pytest.fixture
def user_client(client):
    register(client)
    return client


def promote_admin(email: str):
    with psycopg.connect(TEST_DB, autocommit=True) as c:
        c.execute("INSERT INTO admin_users (user_id) SELECT id FROM users WHERE email = %s", (email,))


def sql(query: str, params=None):
    with psycopg.connect(TEST_DB, autocommit=True) as c:
        cur = c.execute(query, params)
        try:
            return cur.fetchall()
        except psycopg.ProgrammingError:
            return None
