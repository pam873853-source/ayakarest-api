/* AYAKA API — Analytics view (Chart.js, real DB data, 4s polling handled by dashboard.js) */
(function () {
  "use strict";
  const { api, $, $$, esc, fmtNum, animateCount } = window.Ayaka;
  const Dash = window.Dash;
  let range = "minute", last = null;
  const RANGE_KEY = { minute: "requests_per_minute", hour: "requests_per_hour", day: "requests_per_day" };

  function draw(d) {
    const C = window.AyakaCharts;
    $$("[data-an]").forEach((el) => animateCount(el, d.totals[el.dataset.an] || 0));
    if (!C) { $("#ch-requests").parentElement.innerHTML = '<p class="callout danger">Chart.js gagal dimuat dari CDN. Periksa koneksi internet.</p>'; return; }
    const req = C.series(d.charts[RANGE_KEY[range]], range);
    C.render("ch-requests", "line", req.labels, [{ label: "Request", data: req.data, backgroundColor: "rgba(255,214,0,.45)" }]);
    const sf = d.charts.success_vs_failed;
    C.render("ch-success", "bar", sf.map((r) => C.label(r.bucket, "day")), [
      { label: "Berhasil", data: sf.map((r) => r.success), backgroundColor: "#3DDC84" },
      { label: "Gagal", data: sf.map((r) => r.failed), backgroundColor: "#FF5A5A" }], { stacked: true });
    const k = C.series(d.charts.keys_generated_per_day, "day");
    C.render("ch-keys", "bar", k.labels, [{ label: "Key dibuat", data: k.data, backgroundColor: "#7CC4FF" }]);
    const v = C.series(d.charts.visitors_per_day, "day");
    C.render("ch-visitors", "line", v.labels, [{ label: "Visitor unik", data: v.data, backgroundColor: "rgba(255,158,205,.45)" }]);
    const p = C.series(d.charts.premium_activations_per_day, "day");
    C.render("ch-premium", "bar", p.labels, [{ label: "Aktivasi", data: p.data, backgroundColor: "#FFD600" }]);
    $("#an-top").innerHTML = d.top_endpoints.map((t) => `<tr><td>${Dash.methodBadge(t.method)}</td><td><code>${esc(t.endpoint)}</code></td><td class="mono">${fmtNum(t.hits)}</td></tr>`).join("")
      || `<tr><td colspan="3" class="muted">Belum ada request tercatat.</td></tr>`;
  }
  async function load() {
    const r = await api("/api/analytics");
    if (!r.ok) { $("#an-top").innerHTML = Dash.errRow(3, r); return; }
    last = r.data; draw(last);
  }
  document.addEventListener("DOMContentLoaded", () => {
    $("#an-range").addEventListener("click", (e) => {
      const b = e.target.closest("button[data-range]");
      if (!b) return;
      range = b.dataset.range;
      $$("#an-range button").forEach((x) => x.classList.toggle("on", x === b));
      if (last) draw(last);
    });
  });
  Dash.register("analytics", { load, poll: load });
})();
