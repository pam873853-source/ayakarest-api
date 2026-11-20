from conftest import PASSWORD, make_client, make_key, promote_admin, register, sql


def test_analytics_reflect_database(user_client):
    a0 = user_client.get("/api/analytics").json()["data"]["totals"]
    k = make_key(user_client)
    with make_client() as anon:
        for _ in range(3):
            anon.get("/api/user/profile", headers={"X-API-Key": k["api_key"]})
        anon.get("/api/keys/00000000-0000-0000-0000-000000000000", headers={"X-API-Key": k["api_key"]})
    a1 = user_client.get("/api/analytics").json()["data"]
    t = a1["totals"]
    assert t["api_keys_generated"] == a0["api_keys_generated"] + 1
    assert t["requests_success"] >= 3 and t["requests_failed"] >= 1
    assert t["api_requests"] > a0["api_requests"]
    assert len(a1["charts"]["requests_per_minute"]) == 60
    assert sum(b["value"] for b in a1["charts"]["requests_per_minute"]) >= 4
    assert len(a1["charts"]["requests_per_day"]) == 30


def test_visitor_tracking_unique(client):
    for _ in range(3):
        client.post("/api/track", json={"path": "/"})
    client.post("/api/track", json={"path": "/documentation"})
    rows = sql("SELECT count(DISTINCT visitor_hash), sum(page_views) FROM visitor_analytics")[0]
    assert rows[0] == 1 and rows[1] == 4
    client.post("/api/track", json={"path": "/"}, headers={"DNT": "1"})
    assert sql("SELECT sum(page_views) FROM visitor_analytics")[0][0] == 4


def test_logs_endpoint_filters_and_csv(user_client):
    k = make_key(user_client)
    with make_client() as anon:
        anon.get("/api/user/profile", headers={"X-API-Key": k["api_key"]})
        anon.get("/api/keys/bad-id", headers={"X-API-Key": k["api_key"]})
    all_ = user_client.get("/api/logs").json()["data"]
    assert all_["total"] >= 2
    failed = user_client.get("/api/logs?status=4xx").json()["data"]["items"]
    assert failed and all(i["status_code"] >= 400 for i in failed)
    one = user_client.get(f"/api/logs/{all_['items'][0]['request_id']}")
    assert one.status_code == 200
    csv = user_client.get("/api/logs/export.csv")
    assert csv.status_code == 200 and csv.text.startswith("request_id,")


def test_admin_access_control(user_client):
    assert user_client.get("/api/admin/overview").status_code == 403
    r = user_client.get("/admin", follow_redirects=False)
    assert r.status_code == 302
    with make_client() as adm:
        register(adm, "ayaka")
        promote_admin("ayaka@example.com")
        adm.cookies.clear()
        adm.post("/api/auth/login", json={"email": "ayaka@example.com", "password": PASSWORD})
        assert adm.get("/api/admin/overview").status_code == 200
        assert adm.get("/admin", follow_redirects=False).status_code == 200
        users = adm.get("/api/admin/users").json()["data"]["items"]
        alice = next(u for u in users if u["email"] == "alice@example.com")
        # suspend → alice session dies & her API keys stop working
        assert adm.spost(f"/api/admin/users/{alice['id']}/suspend").status_code == 200
        assert user_client.get("/api/auth/me").status_code == 401
        assert adm.spost(f"/api/admin/users/{alice['id']}/activate").status_code == 200
        # delete needs matching confirmation
        r = adm.sdelete(f"/api/admin/users/{alice['id']}", json={"confirm_email": "wrong@example.com"})
        assert r.status_code == 422
        r = adm.sdelete(f"/api/admin/users/{alice['id']}", json={"confirm_email": "alice@example.com"})
        assert r.status_code == 200
        actions = {a for (a,) in sql("SELECT action FROM audit_logs WHERE actor_type='admin'")}
        assert {"admin.user_suspended", "admin.user_activated", "admin.user_deleted"} <= actions


def test_maintenance_mode(user_client):
    k = make_key(user_client)
    with make_client() as adm:
        register(adm, "ayaka")
        promote_admin("ayaka@example.com")
        adm.cookies.clear()
        adm.post("/api/auth/login", json={"email": "ayaka@example.com", "password": PASSWORD})
        r = adm.sput("/api/admin/maintenance", json={"enabled": True, "message": "Upgrade database"})
        assert r.status_code == 200 and r.json()["data"]["active"] is True
        from ayaka.services import settings_store
        settings_store.clear_cache()
        with make_client() as anon:
            r = anon.get("/api/user/profile", headers={"X-API-Key": k["api_key"]})
            assert r.status_code == 503 and r.json()["error"]["code"] == "MAINTENANCE_MODE"
            assert anon.get("/api/health").status_code == 200
            assert anon.get("/api/system/status").json()["data"]["maintenance"]["active"] is True
        # admin keeps access
        assert adm.get("/api/admin/overview").status_code == 200
        assert adm.get("/api/keys").status_code == 200
        r = user_client.get("/dashboard", follow_redirects=False)
        assert r.status_code == 302 and r.headers["location"] == "/maintenance"
        adm.sput("/api/admin/maintenance", json={"enabled": False})
        settings_store.clear_cache()
        with make_client() as anon:
            assert anon.get("/api/user/profile", headers={"X-API-Key": k["api_key"]}).status_code == 200
    assert {"admin.maintenance_enabled", "admin.maintenance_disabled"} <= {
        a for (a,) in sql("SELECT action FROM audit_logs")}


def test_consistent_error_envelope(client):
    r = client.get("/api/does-not-exist")
    assert r.status_code == 404
    b = r.json()
    assert b["success"] is False and b["error"]["code"] == "NOT_FOUND"
    r = client.post("/api/auth/login", json={})
    assert r.status_code == 422 and r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_request_size_limit(client):
    r = client.post("/api/auth/login", content=b"x" * 1_100_000, headers={"Content-Type": "application/json"})
    assert r.status_code == 413
