/* AYAKA API — public status page (real data from /api/status) */
(function () {
  "use strict";
  const { api, $, esc, fmtNum } = window.Ayaka;
  const LABEL = { operational: "Semua sistem berjalan normal", maintenance: "Sedang maintenance", outage: "Gangguan terdeteksi" };
  const COMP = { api: "REST API (FastAPI)", database: "Database (Neon PostgreSQL)", email: "Email (Resend)" };
  const STATE = { operational: ["ok", "Operational"], ok: ["ok", "Operational"], configured: ["ok", "Terkonfigurasi"],
    not_configured: ["warn", "Belum dikonfigurasi"], error: ["bad", "Gangguan"], down: ["bad", "Gangguan"] };
  let timer;

  async function load() {
    const r = await api("/api/status", { handleAuth: false });
    $("#st-updated").textContent = new Date().toLocaleTimeString("id-ID");
    const d = r.data;
    if (!r.ok || !d) {
      $("#st-dot").className = "status-dot bad";
      $("#st-title").textContent = r.status ? (r.message || "Gangguan terdeteksi") : "Server tidak dapat dihubungi";
      return;
    }
    $("#st-dot").className = "status-dot " + (d.overall === "operational" ? "ok" : d.overall === "maintenance" ? "warn" : "bad");
    $("#st-title").textContent = LABEL[d.overall] || d.overall;
    $("#st-req").textContent = fmtNum(d.last_24h.requests);
    $("#st-rate").textContent = d.last_24h.success_rate + "%";
    $("#st-ms").textContent = Math.round(d.last_24h.avg_response_ms || 0) + " ms";
    $("#st-comps").innerHTML = Object.entries(d.components).map(([k, v]) => {
      const [cls, txt] = STATE[v] || ["bad", v];
      return `<div class="card comp"><strong>${esc(COMP[k] || k)}</strong><span class="row" style="gap:8px"><span class="status-dot ${cls}" style="width:14px;height:14px;border-width:2px"></span>${esc(txt)}</span></div>`;
    }).join("");
    $("#st-bars").innerHTML = (d.daily || []).map((x) => {
      const rate = x.total ? x.errors / x.total : 0;
      const cls = !x.total ? "none" : rate >= 0.05 ? "bad" : x.errors ? "err" : "";
      return `<span class="${cls}" title="${esc(x.day.slice(0, 10))}: ${x.total} request, ${x.errors} error 5xx"></span>`;
    }).join("");
  }
  function loop() { clearTimeout(timer); if (!document.hidden) load().finally(() => { timer = setTimeout(loop, 15000); }); }
  document.addEventListener("visibilitychange", () => { if (!document.hidden) loop(); else clearTimeout(timer); });
  document.addEventListener("DOMContentLoaded", loop);
})();
