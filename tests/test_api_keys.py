import re

from conftest import make_client, make_key, register, sql


def test_generate_key_format_and_hash(user_client):
    k = make_key(user_client)
    raw = k["api_key"]
    assert re.fullmatch(r"ayaka_live_[A-Za-z0-9]{40}", raw)
    rows = sql("SELECT key_hash FROM api_keys")
    assert rows[0][0] != raw and raw not in str(rows)
    # Listing never exposes the raw key again
    lst = user_client.get("/api/keys").json()["data"]["items"]
    assert "api_key" not in lst[0] and raw not in str(lst)
    detail = user_client.get(f"/api/keys/{k['id']}").json()["data"]
    assert raw not in str(detail)


def test_valid_key_accepted_invalid_rejected(user_client):
    raw = make_key(user_client)["api_key"]
    with make_client() as anon:
        r = anon.get("/api/user/profile", headers={"X-API-Key": raw})
        assert r.status_code == 200 and r.json()["data"]["email"] == "alice@example.com"
        r = anon.get("/api/user/profile", headers={"X-API-Key": raw[:-1] + ("A" if raw[-1] != "A" else "B")})
        assert r.status_code == 401 and r.json()["error"]["code"] == "INVALID_API_KEY"
        r = anon.get("/api/user/profile", headers={"X-API-Key": "garbage"})
        assert r.status_code == 401
        r = anon.get("/api/user/profile")
        assert r.status_code == 401


def test_key_in_url_rejected(user_client):
    raw = make_key(user_client)["api_key"]
    with make_client() as anon:
        r = anon.get(f"/api/user/profile?api_key={raw}")
        assert r.status_code == 400 and r.json()["error"]["code"] == "API_KEY_IN_URL"


def test_revoked_key_rejected(user_client):
    k = make_key(user_client)
    r = user_client.sdelete(f"/api/keys/{k['id']}")
    assert r.status_code == 200 and r.json()["data"]["status"] == "revoked"
    with make_client() as anon:
        r = anon.get("/api/user/profile", headers={"X-API-Key": k["api_key"]})
        assert r.status_code == 401 and r.json()["error"]["code"] == "API_KEY_REVOKED"


def test_expired_key_rejected(user_client):
    k = make_key(user_client, expires_in_days=1)
    sql("UPDATE api_keys SET expires_at = now() - interval '1 second' WHERE id = %s", (k["id"],))
    with make_client() as anon:
        r = anon.get("/api/user/profile", headers={"X-API-Key": k["api_key"]})
        assert r.status_code == 401 and r.json()["error"]["code"] == "API_KEY_EXPIRED"
    assert user_client.get(f"/api/keys/{k['id']}").json()["data"]["status"] == "expired"


def test_permission_enforced(user_client):
    k = make_key(user_client, perms=["profile:read"])
    with make_client() as anon:
        r = anon.get("/api/keys", headers={"X-API-Key": k["api_key"]})
        assert r.status_code == 403 and r.json()["error"]["code"] == "INSUFFICIENT_PERMISSION"
        r = anon.post("/api/am/send", headers={"X-API-Key": k["api_key"]}, json={"email": "c@example.com"})
        assert r.status_code == 403


def test_cross_user_isolation(user_client):
    alice_key = make_key(user_client)
    with make_client() as bob:
        register(bob, "bob")
        bob_key = make_key(bob)
        # Bob's session cannot see/revoke Alice's key
        assert bob.get(f"/api/keys/{alice_key['id']}").status_code == 404
        assert bob.sdelete(f"/api/keys/{alice_key['id']}").status_code == 404
        # Bob's API key cannot read Alice's key either
        with make_client() as anon:
            r = anon.get(f"/api/keys/{alice_key['id']}", headers={"X-API-Key": bob_key["api_key"]})
            assert r.status_code == 404
            lst = anon.get("/api/keys", headers={"X-API-Key": bob_key["api_key"]}).json()["data"]["items"]
            assert [i["id"] for i in lst] == [bob_key["id"]]


def test_key_management_requires_session(user_client):
    raw = make_key(user_client)["api_key"]
    with make_client() as anon:
        r = anon.post("/api/keys/generate", headers={"X-API-Key": raw}, json={"name": "x"})
        assert r.status_code == 403 and r.json()["error"]["code"] == "SESSION_REQUIRED"


def test_regenerate(user_client):
    k = make_key(user_client)
    r = user_client.spost(f"/api/keys/{k['id']}/regenerate")
    assert r.status_code == 201
    new = r.json()["data"]
    assert new["api_key"] != k["api_key"] and new["rotated_from"] == k["id"]
    with make_client() as anon:
        assert anon.get("/api/user/profile", headers={"X-API-Key": k["api_key"]}).status_code == 401
        assert anon.get("/api/user/profile", headers={"X-API-Key": new["api_key"]}).status_code == 200


def test_rate_limit_per_key(user_client):
    k = make_key(user_client, rate_limit_per_minute=3)
    with make_client() as anon:
        codes = [anon.get("/api/user/profile", headers={"X-API-Key": k["api_key"]}).status_code for _ in range(4)]
        assert codes[:3] == [200, 200, 200] and codes[3] == 429


def test_logs_never_store_secrets(user_client):
    raw = make_key(user_client)["api_key"]
    with make_client() as anon:
        anon.get("/api/user/profile", headers={"X-API-Key": raw})
    dump = str(sql("SELECT * FROM api_request_logs"))
    assert raw not in dump and "api_request_logs" not in dump
    assert "/api/user/profile" in dump


def test_delete_via_api_key_with_permission(user_client):
    target = make_key(user_client)
    k = make_key(user_client, perms=["keys:revoke"])
    with make_client() as anon:
        r = anon.delete(f"/api/keys/{target['id']}", headers={"X-API-Key": k["api_key"]})
        assert r.status_code == 200 and r.json()["data"]["status"] == "revoked"
        noperm = make_key(user_client, perms=["profile:read"])
        r = anon.delete(f"/api/keys/{k['id']}", headers={"X-API-Key": noperm["api_key"]})
        assert r.status_code == 403
