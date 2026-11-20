/* AYAKA API — API Playground: real requests, cookie-less (credentials: "omit"), key never stored */
(function () {
  "use strict";
  const { $, esc, toast, copyText, icon, setLoading } = window.Ayaka;
  const PRESETS = [
    ["GET", "/api/health", null], ["GET", "/api", null], ["GET", "/api/user/profile", null], ["GET", "/api/keys", null],
    ["GET", "/api/analytics", null], ["GET", "/api/logs?per_page=5", null],
    ["POST", "/api/am/send", { email: "user@example.com", plan: "premium" }],
    ["GET", "/api/am/status?email=user@example.com", null],
    ["POST", "/api/am/renew", { email: "user@example.com", duration_days: 30 }],
    ["POST", "/api/am/revoke", { email: "user@example.com", reason: "Testing" }],
    ["DELETE", "/api/keys/KEY_ID", { reason: "Testing" }],
  ];
  let lastText = "";

  function highlight(json) {
    return esc(json)
      .replace(/(&quot;[^&]*?&quot;)(\s*:)/g, '<span class="t-key">$1</span>$2')
      .replace(/:\s(&quot;.*?&quot;)/g, ': <span class="t-str">$1</span>')
      .replace(/:\s(true|false|null|-?\d+\.?\d*)/g, ': <span class="t-num">$1</span>');
  }
  function apply(i) {
    const [m, u, b] = PRESETS[i];
    $("#pg-method").value = m; $("#pg-url").value = u;
    $("#pg-body").value = b ? JSON.stringify(b, null, 2) : "";
  }
  async function send(e) {
    e.preventDefault();
    const method = $("#pg-method").value;
    let url = $("#pg-url").value.trim();
    const key = $("#pg-key").value.trim();
    const raw = $("#pg-body").value.trim();
    $("#pg-body-err").textContent = "";
    if (!url.startsWith("/api")) { $("#pg-body-err").textContent = "Endpoint harus diawali /api"; return; }
    if (/[?&](api_key|apikey|key|x-api-key)=/i.test(url)) { toast("Jangan kirim API Key di URL. Gunakan kolom X-API-Key.", "error"); return; }
    let body;
    if (raw) {
      try { body = JSON.stringify(JSON.parse(raw)); } catch (err) { $("#pg-body-err").textContent = "JSON tidak valid: " + err.message; return; }
      if (method === "GET") { $("#pg-body-err").textContent = "Request GET tidak boleh memiliki body"; return; }
    }
    const headers = { Accept: "application/json" };
    if (key) headers["X-API-Key"] = key;
    if (body) headers["Content-Type"] = "application/json";
    const btn = $("#pg-send");
    setLoading(btn, true);
    const t0 = performance.now();
    try {
      const res = await fetch(url, { method, headers, body, credentials: "omit", cache: "no-store" });
      const ms = Math.round(performance.now() - t0);
      const text = await res.text();
      let pretty = text;
      try { pretty = JSON.stringify(JSON.parse(text), null, 2); } catch (err) { /* not JSON */ }
      lastText = pretty;
      $("#pg-status").textContent = `${res.status} ${res.statusText || ""}`.trim();
      $("#pg-status").className = "status-pill " + (res.ok ? "ok" : "bad");
      $("#pg-time").textContent = ms + " ms";
      $("#pg-size").textContent = new Blob([text]).size + " B";
      const rid = res.headers.get("X-Request-ID"), rl = res.headers.get("X-RateLimit-Remaining");
      const meta = `<span class="t-dim">// X-Request-ID: ${esc(rid || "—")}${rl !== null ? " · X-RateLimit-Remaining: " + esc(rl) : ""}</span>\n`;
      $("#pg-out").innerHTML = meta + highlight(pretty);
    } catch (err) {
      $("#pg-status").textContent = "ERR"; $("#pg-status").className = "status-pill bad";
      $("#pg-out").textContent = "Gagal terhubung: " + err.message;
      lastText = "";
    } finally { setLoading(btn, false); }
  }
  document.addEventListener("DOMContentLoaded", () => {
    $("#pg-preset").innerHTML = PRESETS.map((p, i) => `<option value="${i}">${p[0]} ${esc(p[1])}</option>`).join("");
    $("#pg-preset").addEventListener("change", (e) => apply(parseInt(e.target.value, 10)));
    $("#pg-preset").value = "2"; apply(2);
    $("#pg-form").addEventListener("submit", send);
    $("#pg-clear").addEventListener("click", () => {
      $("#pg-body").value = ""; $("#pg-key").value = ""; lastText = "";
      $("#pg-status").textContent = "—"; $("#pg-status").className = "status-pill"; $("#pg-time").textContent = "0 ms"; $("#pg-size").textContent = "";
      $("#pg-out").innerHTML = '<span class="t-dim">// Respons akan muncul di sini</span>';
    });
    $("#pg-copy").addEventListener("click", () => (lastText ? copyText(lastText, "Respons disalin") : toast("Belum ada respons", "info")));
    $("#pg-key-toggle").addEventListener("click", () => {
      const i = $("#pg-key"), show = i.type === "password";
      i.type = show ? "text" : "password"; $("#pg-key-toggle").innerHTML = icon(show ? "x" : "eye");
    });
  });
  window.Dash.register("playground", {});
})();
