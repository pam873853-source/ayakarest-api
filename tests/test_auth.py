from conftest import PASSWORD, make_client, register, sql


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True and body["data"]["database"]["status"] == "ok"
    assert "timestamp" in body
    assert r.headers["x-content-type-options"] == "nosniff"


def test_register_success_and_session(client):
    u = register(client)
    assert u["email"] == "alice@example.com"
    me = client.get("/api/auth/me")
    assert me.status_code == 200 and me.json()["data"]["user"]["username"] == "alice"
    # password stored as argon2id hash, never plaintext
    h = sql("SELECT password_hash FROM users")[0][0]
    assert h.startswith("$argon2id$") and PASSWORD not in h


def test_register_duplicate_email_rejected(client):
    register(client)
    with make_client() as c2:
        r = c2.post("/api/auth/register", json={"username": "other", "full_name": "Other", "email": "ALICE@example.com",
                                                "password": PASSWORD, "confirm_password": PASSWORD})
        assert r.status_code == 409 and r.json()["error"]["code"] == "EMAIL_EXISTS"


def test_register_validation(client):
    r = client.post("/api/auth/register", json={"username": "bob", "full_name": "Bob", "email": "bad-email",
                                                "password": PASSWORD, "confirm_password": PASSWORD})
    assert r.status_code == 422 and r.json()["error"]["code"] == "INVALID_EMAIL"
    r = client.post("/api/auth/register", json={"username": "bob", "full_name": "Bob", "email": "b@example.com",
                                                "password": "weak", "confirm_password": "weak"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "WEAK_PASSWORD"
    r = client.post("/api/auth/register", json={"username": "bob", "full_name": "Bob", "email": "b@example.com",
                                                "password": PASSWORD, "confirm_password": PASSWORD + "x"})
    assert r.json()["error"]["code"] == "PASSWORD_MISMATCH"


def test_login_logout_flow(client):
    register(client)
    client.cookies.clear()
    bad = client.post("/api/auth/login", json={"email": "alice@example.com", "password": "Wrong1234"})
    assert bad.status_code == 401 and bad.json()["error"]["code"] == "INVALID_CREDENTIALS"
    good = client.post("/api/auth/login", json={"email": "alice@example.com", "password": PASSWORD,
                                                "remember_me": True})
    assert good.status_code == 200
    set_cookie = good.headers.get("set-cookie", "").lower()
    assert "httponly" in set_cookie and "samesite=lax" in set_cookie
    assert client.get("/api/auth/me").status_code == 200
    # logout without CSRF header is rejected
    assert client.post("/api/auth/logout").status_code == 403
    out = client.spost("/api/auth/logout")
    assert out.status_code == 200
    assert client.get("/api/auth/me").status_code == 401


def test_session_expired(client):
    register(client)
    sql("UPDATE user_sessions SET expires_at = now() - interval '1 minute'")
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/keys").status_code == 401


def test_bruteforce_lockout(client):
    register(client)
    client.cookies.clear()
    for _ in range(5):
        client.post("/api/auth/login", json={"email": "alice@example.com", "password": "Wrong1234"})
    r = client.post("/api/auth/login", json={"email": "alice@example.com", "password": PASSWORD})
    assert r.status_code == 429 and r.json()["error"]["code"] == "ACCOUNT_LOCKED"


def test_csrf_required_for_session_writes(user_client):
    r = user_client.post("/api/keys/generate", json={"name": "x", "permissions": ["profile:read"]})
    assert r.status_code == 403 and r.json()["error"]["code"] == "CSRF_TOKEN_INVALID"


def test_forgot_and_reset_password(client, outbox):
    register(client)
    client.cookies.clear()
    r = client.post("/api/auth/forgot-password", json={"email": "alice@example.com"})
    assert r.status_code == 200 and len(outbox) == 1
    from conftest import extract_token
    token = extract_token(outbox[0]["html"])
    r = client.post("/api/auth/reset-password", json={"token": token, "password": "BaruSekali9",
                                                      "confirm_password": "BaruSekali9"})
    assert r.status_code == 200, r.text
    # one-time
    r = client.post("/api/auth/reset-password", json={"token": token, "password": "BaruSekali9",
                                                      "confirm_password": "BaruSekali9"})
    assert r.status_code == 400
    ok = client.post("/api/auth/login", json={"email": "alice@example.com", "password": "BaruSekali9"})
    assert ok.status_code == 200
    # unknown email gets same generic answer
    r = client.post("/api/auth/forgot-password", json={"email": "nobody@example.com"})
    assert r.status_code == 200


def test_dashboard_page_requires_login(client):
    r = client.get("/dashboard", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"].startswith("/login")
    register(client)
    r = client.get("/dashboard", follow_redirects=False)
    assert r.status_code == 200 and "AYAKA" in r.text
    r = client.get("/login", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == "/dashboard"
