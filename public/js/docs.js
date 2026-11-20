/* AYAKA API — Documentation: generated JS/PHP/Python examples, search, scroll-spy */
(function () {
  "use strict";
  const { esc, $, $$, initTabs, hydrateIcons } = window.Ayaka;
  const BASE = location.origin;
  const TS = "2026-01-01T00:00:00Z";
  const ok = (message, data) => ({ success: true, message, data, timestamp: TS });
  const fail = (message, code, extra) => ({ success: false, message, error: Object.assign({ code }, extra || {}), timestamp: TS });

  const EX = {
    profile: { fn: "getProfile", method: "GET", path: "/api/user/profile",
      success: ok("Request successful", { id: "8c1d…", username: "olpi", full_name: "OLPI STORE", email: "user@example.com", status: "active", auth_type: "api_key", api_key: { id: "f3a9…", name: "Server Produksi", permissions: ["profile:read"] } }),
      failure: [401, fail("Invalid API Key", "INVALID_API_KEY")] },
    keys: { fn: "listKeys", method: "GET", path: "/api/keys",
      success: ok("Request successful", { items: [{ id: "f3a9…", name: "Server Produksi", prefix: "ayaka_live_Ab12", status: "active", permissions: ["keys:read"], last_used_at: TS }], total: 1 }),
      failure: [403, fail("API Key tidak memiliki permission: keys:read", "INSUFFICIENT_PERMISSION")] },
    send: { fn: "sendMagicLink", method: "POST", path: "/api/am/send", body: { email: "user@example.com", plan: "premium" },
      success: ok("Magic Link sent successfully", { email: "user@example.com", plan: "premium", duration_days: 30, expires_in: 900, email_id: "re_…" }),
      failure: [429, fail("Terlalu banyak Magic Link untuk email ini. Coba lagi nanti.", "RATE_LIMITED")] },
    delete: { fn: "revokeKey", method: "DELETE", path: "/api/keys/KEY_ID", body: { reason: "Key bocor" },
      success: ok("API Key berhasil dicabut", { id: "KEY_ID", status: "revoked", revoked_at: TS }),
      failure: [404, fail("API Key tidak ditemukan", "NOT_FOUND")] },
    verify: { fn: "verifyToken", method: "POST", path: "/api/am/verif", body: { token: "TOKEN_DARI_EMAIL" }, noKey: true,
      success: ok("Premium activated", { email: "user@example.com", premium: true, status: "active", plan: "premium", activated_at: TS, expires_at: "2026-01-31T00:00:00Z" }),
      failure: [410, fail("Magic Link sudah kedaluwarsa. Minta tautan baru.", "TOKEN_EXPIRED")] },
    status: { fn: "premiumStatus", method: "GET", path: "/api/am/status", query: { email: "user@example.com" },
      success: ok("Request successful", { email: "user@example.com", premium: true, status: "active", plan: "premium", activated_at: TS, expires_at: "2026-01-31T00:00:00Z", revoked_at: null }),
      failure: [422, fail("Format email tidak valid", "INVALID_EMAIL")] },
    renew: { fn: "renewPremium", method: "POST", path: "/api/am/renew", body: { email: "user@example.com", duration_days: 30 },
      success: ok("Premium renewed successfully", { email: "user@example.com", premium: true, status: "active", expires_at: "2026-03-02T00:00:00Z" }),
      failure: [404, fail("Belum ada Premium untuk email ini. Kirim Magic Link dulu.", "SUBSCRIPTION_NOT_FOUND")] },
    revoke: { fn: "revokePremium", method: "POST", path: "/api/am/revoke", body: { email: "user@example.com", reason: "Refund" },
      success: ok("Premium revoked successfully", { email: "user@example.com", premium: false, status: "revoked", revoked_at: TS }),
      failure: [409, fail("Premium sudah dicabut sebelumnya", "ALREADY_REVOKED")] },
  };

  const J = (o, ind) => JSON.stringify(o, null, 2).split("\n").join("\n" + (ind || ""));
  const pyLit = (o, ind) => J(o, ind).replace(/\btrue\b/g, "True").replace(/\bfalse\b/g, "False").replace(/\bnull\b/g, "None");
  const phpArr = (o, ind) => {
    const pad = ind || "";
    const items = Object.entries(o).map(([k, v]) => `${pad}    "${k}" => ${typeof v === "number" ? v : JSON.stringify(v)},`);
    return "[\n" + items.join("\n") + "\n" + pad + "]";
  };
  const qs = (q) => (q ? "?" + Object.entries(q).map(([k, v]) => `${k}=${encodeURIComponent(v)}`).join("&") : "");

  function jsCode(e) {
    const hasBody = !!e.body;
    const url = e.query ? `\`\${BASE_URL}${e.path}?${Object.keys(e.query).map((k) => `${k}=\${encodeURIComponent(${JSON.stringify(e.query[k])})}`).join("&")}\`` : `\`\${BASE_URL}${e.path}\``;
    const headers = [];
    if (hasBody) headers.push(`"Content-Type": "application/json"`);
    if (!e.noKey) headers.push(`"X-API-Key": API_KEY`);
    return `// Node.js 18+ (fetch bawaan) — jalankan di server, bukan di browser
const BASE_URL = "${BASE}";
${e.noKey ? "" : `const API_KEY = process.env.AYAKA_API_KEY || "ayaka_live_YOUR_SECRET_KEY";\n`}
async function ${e.fn}() {
  const response = await fetch(${url}, {
    method: "${e.method}",
    headers: { ${headers.join(", ")} }${hasBody ? `,\n    body: JSON.stringify(${J(e.body, "    ")})` : ""}
  });
  const result = await response.json();
  if (!response.ok || !result.success) {
    throw new Error(\`[\${response.status}] \${result.error?.code}: \${result.message}\`);
  }
  return result.data;
}

${e.fn}()
  .then((data) => console.log("Berhasil:", data))
  .catch((err) => console.error("Gagal:", err.message));`;
  }

  function phpCode(e) {
    const hdr = [];
    if (e.body) hdr.push(`"Content-Type: application/json"`);
    if (!e.noKey) hdr.push(`"X-API-Key: " . $apiKey`);
    hdr.push(`"Accept: application/json"`);
    const url = e.query ? `$baseUrl . "${e.path}?" . http_build_query(${phpArr(e.query)})` : `$baseUrl . "${e.path}"`;
    return `<?php
$baseUrl = "${BASE}";
${e.noKey ? "" : `$apiKey  = getenv("AYAKA_API_KEY") ?: "ayaka_live_YOUR_SECRET_KEY";\n`}
$ch = curl_init(${url});
curl_setopt_array($ch, [
    CURLOPT_RETURNTRANSFER => true,
    CURLOPT_CUSTOMREQUEST  => "${e.method}",
    CURLOPT_TIMEOUT        => 15,
    CURLOPT_HTTPHEADER     => [${hdr.join(", ")}],${e.body ? `\n    CURLOPT_POSTFIELDS     => json_encode(${phpArr(e.body, "    ")}),` : ""}
]);

$response = curl_exec($ch);
if ($response === false) {
    die("Koneksi gagal: " . curl_error($ch));
}
$status = curl_getinfo($ch, CURLINFO_HTTP_CODE);
curl_close($ch);

$result = json_decode($response, true);
if ($status >= 400 || empty($result["success"])) {
    echo "Gagal [$status] " . ($result["error"]["code"] ?? "") . ": " . ($result["message"] ?? "");
} else {
    print_r($result["data"]);
}`;
  }

  function pyCode(e) {
    const hdr = [];
    if (!e.noKey) hdr.push(`"X-API-Key": API_KEY`);
    const args = [`f"{BASE_URL}${e.path}"`, `headers={${hdr.join(", ")}}`];
    if (e.query) args.push(`params=${pyLit(e.query, "    ")}`);
    if (e.body) args.push(`json=${pyLit(e.body, "    ")}`);
    args.push("timeout=15");
    return `import os
import requests  # pip install requests

BASE_URL = "${BASE}"
${e.noKey ? "" : `API_KEY = os.getenv("AYAKA_API_KEY", "ayaka_live_YOUR_SECRET_KEY")\n`}

def ${e.fn.replace(/[A-Z]/g, (c) => "_" + c.toLowerCase())}():
    response = requests.${e.method.toLowerCase()}(
        ${args.join(",\n        ")},
    )
    result = response.json()
    if not response.ok or not result.get("success"):
        raise RuntimeError(f"[{response.status_code}] {result.get('error', {}).get('code')}: {result.get('message')}")
    return result["data"]


if __name__ == "__main__":
    print(${e.fn.replace(/[A-Z]/g, (c) => "_" + c.toLowerCase())}())`;
  }

  function curlCode(e) {
    const parts = [`curl -X ${e.method} "${BASE}${e.path}${qs(e.query)}"`];
    if (!e.noKey) parts.push(`-H "X-API-Key: $AYAKA_API_KEY"`);
    if (e.body) parts.push(`-H "Content-Type: application/json"`, `-d '${JSON.stringify(e.body)}'`);
    return parts.join(" \\\n  ");
  }

  const WEBHOOK = {
    js: `// Express.js — verifikasi signature webhook AYAKA
import express from "express";
import crypto from "node:crypto";

const app = express();
const SECRET = process.env.AYAKA_WEBHOOK_SECRET; // whsec_... (ditampilkan sekali saat dibuat)

app.post("/ayaka-webhook", express.text({ type: "application/json" }), (req, res) => {
  const ts = req.get("X-Ayaka-Timestamp");
  const sig = req.get("X-Ayaka-Signature") || "";
  if (!ts || Math.abs(Date.now() / 1000 - Number(ts)) > 300) return res.status(400).send("stale");
  const expected = "sha256=" + crypto.createHmac("sha256", SECRET).update(\`\${ts}.\${req.body}\`).digest("hex");
  const a = Buffer.from(sig), b = Buffer.from(expected);
  if (a.length !== b.length || !crypto.timingSafeEqual(a, b)) return res.status(401).send("bad signature");
  const event = JSON.parse(req.body);
  console.log(req.get("X-Ayaka-Event"), event.data);
  res.sendStatus(200);
});
app.listen(3000);`,
    php: `<?php
$secret = getenv("AYAKA_WEBHOOK_SECRET");
$body   = file_get_contents("php://input");
$ts     = $_SERVER["HTTP_X_AYAKA_TIMESTAMP"] ?? "";
$sig    = $_SERVER["HTTP_X_AYAKA_SIGNATURE"] ?? "";

if (!ctype_digit($ts) || abs(time() - (int)$ts) > 300) { http_response_code(400); exit("stale"); }
$expected = "sha256=" . hash_hmac("sha256", $ts . "." . $body, $secret);
if (!hash_equals($expected, $sig)) { http_response_code(401); exit("bad signature"); }

$event = json_decode($body, true);
error_log(($_SERVER["HTTP_X_AYAKA_EVENT"] ?? "") . " " . json_encode($event["data"]));
http_response_code(200);`,
    py: `# FastAPI — verifikasi signature webhook AYAKA
import hashlib, hmac, os, time
from fastapi import FastAPI, Request, HTTPException

app = FastAPI()
SECRET = os.environ["AYAKA_WEBHOOK_SECRET"].encode()

@app.post("/ayaka-webhook")
async def ayaka_webhook(request: Request):
    body = (await request.body()).decode()
    ts = request.headers.get("X-Ayaka-Timestamp", "")
    sig = request.headers.get("X-Ayaka-Signature", "")
    if not ts.isdigit() or abs(time.time() - int(ts)) > 300:
        raise HTTPException(400, "stale")
    expected = "sha256=" + hmac.new(SECRET, f"{ts}.{body}".encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        raise HTTPException(401, "bad signature")
    event = await request.json()
    print(request.headers.get("X-Ayaka-Event"), event["data"])
    return {"ok": True}`,
  };

  function codeCard(id, panes) {
    const labels = { js: "JavaScript", php: "PHP", py: "Python", curl: "cURL", ok: "Respons berhasil", err: "Respons gagal" };
    const tabs = Object.keys(panes).map((k) => `<button class="tab" type="button" role="tab" data-tab="${k}">${labels[k]}</button>`).join("");
    const pre = Object.entries(panes).map(([k, v]) => `<pre data-pane="${k}"><code>${esc(v)}</code></pre>`).join("");
    return `<div class="code-card" data-tabs="${id}"><div class="tabs" role="tablist">${tabs}<button class="tab tab-copy" type="button">Copy</button></div>${pre}</div>`;
  }

  function render() {
    $$("[data-example]").forEach((el) => {
      const key = el.dataset.example;
      if (key === "webhook") { el.innerHTML = codeCard("lang", WEBHOOK); return; }
      const e = EX[key];
      if (!e) return;
      const [st, f] = e.failure;
      el.innerHTML = `<div class="row" style="margin:6px 0 12px"><span class="badge m-${e.method.toLowerCase()}">${e.method}</span><code class="mono" style="font-weight:700">${esc(e.path + (e.query ? "?email=…" : ""))}</code></div>` +
        codeCard("lang", { js: jsCode(e), php: phpCode(e), py: pyCode(e), curl: curlCode(e) }) +
        `<div style="margin-top:14px">` + codeCard("resp-" + key, { ok: "HTTP 200\n" + J(e.success), err: `HTTP ${st}\n` + J(f) }) + `</div>`;
    });
    initTabs($(".docs-content"));
    hydrateIcons();
  }

  function search() {
    const q = $("#docs-q");
    if (!q) return;
    const sections = $$("[data-doc]");
    q.addEventListener("input", () => {
      const term = q.value.trim().toLowerCase();
      let hits = 0;
      sections.forEach((s) => {
        const match = !term || s.textContent.toLowerCase().includes(term);
        s.classList.toggle("hidden", !match);
        if (match) hits++;
      });
      $$(".docs-nav a").forEach((a) => {
        const s = $(a.getAttribute("href"));
        a.classList.toggle("hidden", !!s && s.classList.contains("hidden"));
      });
      $("#docs-noresult").classList.toggle("hidden", hits > 0);
    });
  }

  function scrollSpy() {
    const links = $$(".docs-nav a[href^='#']");
    if (!("IntersectionObserver" in window)) return;
    const io = new IntersectionObserver((entries) => {
      entries.forEach((en) => {
        if (en.isIntersecting) links.forEach((a) => a.classList.toggle("active", a.getAttribute("href") === "#" + en.target.id));
      });
    }, { rootMargin: "-90px 0px -70% 0px" });
    $$(".docs-content section[id]").forEach((s) => io.observe(s));
  }

  document.addEventListener("DOMContentLoaded", () => { render(); search(); scrollSpy(); });
})();
