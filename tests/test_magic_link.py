from conftest import extract_token, make_client, make_key, register, sql


def _send(anon, key, email="cust@example.com", **extra):
    return anon.post("/api/am/send", headers={"X-API-Key": key}, json={"email": email, "plan": "premium", **extra})


def test_full_premium_lifecycle(user_client, outbox):
    key = make_key(user_client)["api_key"]
    with make_client() as anon:
        r = _send(anon, key)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["data"]["expires_in"] == 900 and "token" not in str(body["data"]).lower().replace("expires", "")
        assert len(outbox) == 1 and outbox[0]["to"] == ["cust@example.com"]
        token = extract_token(outbox[0]["html"])
        # only the hash is in DB
        assert token not in str(sql("SELECT * FROM magic_link_tokens"))

        st = anon.get("/api/am/status?email=cust@example.com", headers={"X-API-Key": key}).json()["data"]
        assert st["premium"] is False and st["status"] == "none"

        # GET shows confirmation page, does NOT consume the token
        page = anon.get(f"/api/am/verif?token={token}")
        assert page.status_code == 200 and "Verify Account" in page.text
        # POST (form) verifies
        done = anon.post("/api/am/verif", data={"token": token})
        assert done.status_code == 200 and "Premium aktif" in done.text
        # reuse rejected
        again = anon.post("/api/am/verif", json={"token": token})
        assert again.status_code == 409 and again.json()["error"]["code"] == "TOKEN_ALREADY_USED"

        st = anon.get("/api/am/status?email=cust@example.com", headers={"X-API-Key": key}).json()["data"]
        assert st["premium"] is True and st["status"] == "active"
        first_exp = st["expires_at"]

        r = anon.post("/api/am/renew", headers={"X-API-Key": key},
                      json={"email": "cust@example.com", "duration_days": 30})
        assert r.status_code == 200 and r.json()["data"]["expires_at"] > first_exp

        for bad in (-5, 0, 9999):
            r = anon.post("/api/am/renew", headers={"X-API-Key": key},
                          json={"email": "cust@example.com", "duration_days": bad})
            assert r.status_code == 422

        r = anon.post("/api/am/revoke", headers={"X-API-Key": key}, json={"email": "cust@example.com"})
        assert r.status_code == 200 and r.json()["data"]["status"] == "revoked"
        st = anon.get("/api/am/status?email=cust@example.com", headers={"X-API-Key": key}).json()["data"]
        assert st["premium"] is False and st["status"] == "revoked"
        r = anon.post("/api/am/revoke", headers={"X-API-Key": key}, json={"email": "cust@example.com"})
        assert r.status_code == 409
    actions = [a[0] for a in sql("SELECT action FROM premium_renewal_logs ORDER BY id")]
    assert actions == ["activate", "renew", "revoke"]
    assert {t for (t,) in sql("SELECT template FROM email_logs")} >= {"magic_link", "premium_activated",
                                                                      "premium_renewed", "premium_revoked"}


def test_expired_token_rejected(user_client, outbox):
    key = make_key(user_client)["api_key"]
    with make_client() as anon:
        _send(anon, key)
        token = extract_token(outbox[0]["html"])
        sql("UPDATE magic_link_tokens SET expires_at = now() - interval '1 second'")
        r = anon.post("/api/am/verif", json={"token": token})
        assert r.status_code == 410 and r.json()["error"]["code"] == "TOKEN_EXPIRED"


def test_invalid_token(client):
    r = client.post("/api/am/verif", json={"token": "x" * 43})
    assert r.status_code == 400 and r.json()["error"]["code"] == "INVALID_TOKEN"


def test_tenant_isolation_premium(user_client, outbox):
    key_a = make_key(user_client)["api_key"]
    with make_client() as anon:
        _send(anon, key_a)
        anon.post("/api/am/verif", json={"token": extract_token(outbox[0]["html"])})
    with make_client() as bob:
        register(bob, "bob")
        key_b = make_key(bob)["api_key"]
        with make_client() as anon:
            st = anon.get("/api/am/status?email=cust@example.com", headers={"X-API-Key": key_b}).json()["data"]
            assert st["premium"] is False and st["status"] == "none"
            r = anon.post("/api/am/revoke", headers={"X-API-Key": key_b}, json={"email": "cust@example.com"})
            assert r.status_code == 404


def test_email_failure_reported(user_client, monkeypatch):
    from ayaka.services import resend_client
    from conftest import FakeResp
    monkeypatch.setattr(resend_client, "_post", lambda p, k: FakeResp(403, {"message": "domain not verified"}))
    key = make_key(user_client)["api_key"]
    with make_client() as anon:
        r = _send(anon, key)
        assert r.status_code == 502 and r.json()["error"]["code"] == "EMAIL_DELIVERY_FAILED"
        assert "re_test_dummy" not in r.text
    assert sql("SELECT status FROM email_logs")[0][0] == "failed"


def test_premium_permissions(user_client, outbox):
    key = make_key(user_client, perms=["premium:send", "premium:status"])["api_key"]
    with make_client() as anon:
        r = anon.post("/api/am/renew", headers={"X-API-Key": key}, json={"email": "c@example.com", "duration_days": 5})
        assert r.status_code == 403
        r = anon.post("/api/am/revoke", headers={"X-API-Key": key}, json={"email": "c@example.com"})
        assert r.status_code == 403
