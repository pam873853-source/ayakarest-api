"""AYAKA API — contoh integrasi Python 3.9+ (pip install requests). Powered by AYAKA Sync.

Jalankan:  AYAKA_BASE_URL=https://domain-anda.vercel.app AYAKA_API_KEY=ayaka_live_xxx python ayaka_client.py user@example.com
"""
import os
import sys
from urllib.parse import quote

import requests


class AyakaError(Exception):
    def __init__(self, status, code, message, details=None):
        super().__init__(f"[{status} {code}] {message}")
        self.status, self.code, self.details = status, code, details


class AyakaClient:
    def __init__(self, base_url: str, api_key: str, timeout: int = 20):
        self.base_url = base_url.rstrip("/")
        self.s = requests.Session()
        self.s.headers.update({"X-API-Key": api_key, "Accept": "application/json"})
        self.timeout = timeout

    def request(self, method: str, path: str, json=None):
        r = self.s.request(method, self.base_url + path, json=json, timeout=self.timeout)
        try:
            body = r.json()
        except ValueError:
            body = {"success": False, "message": "Respons bukan JSON"}
        if r.status_code >= 400 or not body.get("success"):
            err = body.get("error") or {}
            raise AyakaError(r.status_code, err.get("code"), body.get("message"), err.get("details"))
        return body.get("data")

    def profile(self): return self.request("GET", "/api/user/profile")
    def keys(self): return self.request("GET", "/api/keys")
    def revoke_key(self, key_id): return self.request("DELETE", f"/api/keys/{quote(key_id)}")
    def send_magic_link(self, email, plan="premium", name=None): return self.request("POST", "/api/am/send", {"email": email, "plan": plan, "name": name})
    def status(self, email): return self.request("GET", f"/api/am/status?email={quote(email)}")
    def renew(self, email, days): return self.request("POST", "/api/am/renew", {"email": email, "duration_days": days})
    def revoke_premium(self, email, reason=None): return self.request("POST", "/api/am/revoke", {"email": email, "reason": reason})


if __name__ == "__main__":
    key = os.environ.get("AYAKA_API_KEY")
    if not key:
        sys.exit("Set AYAKA_API_KEY terlebih dahulu")
    c = AyakaClient(os.environ.get("AYAKA_BASE_URL", "http://localhost:8000"), key)
    try:
        print(c.profile())
        if len(sys.argv) > 1:
            print(c.status(sys.argv[1]))
    except AyakaError as e:
        sys.exit(str(e))
