/* AYAKA API — Chart.js helpers (Neo Brutalism styling), shared by dashboard & admin */
(function () {
  "use strict";
  const charts = {};
  function css(v) { return getComputedStyle(document.documentElement).getPropertyValue(v).trim(); }
  function palette() {
    return { ink: css("--text") || "#151515", yellow: "#FFD600", yellow2: "#FFE766", red: "#FF5A5A", green: "#3DDC84",
      blue: "#7CC4FF", pink: "#FF9ECD", grid: css("--surface-2") || "#E8E8E0", muted: css("--muted") || "#5A5A52" };
  }
  function label(bucket, unit) {
    const d = new Date(bucket);
    if (unit === "minute") return d.toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit" });
    if (unit === "hour") return d.toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit" });
    return d.toLocaleDateString("id-ID", { day: "2-digit", month: "short" });
  }
  function baseOptions(stacked) {
    const p = palette();
    return {
      responsive: true, maintainAspectRatio: false, animation: { duration: 350 },
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { display: !!stacked, labels: { color: p.ink, font: { weight: "700", family: "Space Grotesk" }, boxWidth: 14 } },
        tooltip: { backgroundColor: "#151515", titleColor: "#FFD600", bodyColor: "#fff", borderColor: "#FFD600", borderWidth: 2, padding: 10, cornerRadius: 6 },
      },
      scales: {
        x: { stacked: !!stacked, ticks: { color: p.muted, maxRotation: 0, autoSkip: true, maxTicksLimit: 8, font: { family: "JetBrains Mono", size: 10 } }, grid: { display: false }, border: { color: p.ink, width: 2 } },
        y: { stacked: !!stacked, beginAtZero: true, ticks: { color: p.muted, precision: 0, font: { family: "JetBrains Mono", size: 10 } }, grid: { color: p.grid }, border: { color: p.ink, width: 2 } },
      },
    };
  }
  /** Create or update a chart in place (no flicker on polling). */
  function render(id, type, labels, datasets, opts = {}) {
    const el = document.getElementById(id);
    if (!el || !window.Chart) return null;
    const p = palette();
    const ds = datasets.map((d, i) => Object.assign({
      borderColor: p.ink, borderWidth: 2,
      backgroundColor: [p.yellow, p.red, p.blue, p.green, p.pink][i % 5],
      pointRadius: type === "line" ? 0 : undefined, pointHoverRadius: 5, tension: 0.25, fill: type === "line",
      borderRadius: type === "bar" ? 4 : undefined, borderSkipped: false,
    }, d));
    const existing = charts[id];
    if (existing && existing.config.type === type) {
      existing.data.labels = labels;
      ds.forEach((d, i) => { if (existing.data.datasets[i]) { existing.data.datasets[i].data = d.data; } else existing.data.datasets.push(d); });
      existing.data.datasets.length = ds.length;
      existing.update("none");
      return existing;
    }
    if (existing) existing.destroy();
    charts[id] = new window.Chart(el, { type, data: { labels, datasets: ds }, options: Object.assign(baseOptions(opts.stacked), opts.options || {}) });
    return charts[id];
  }
  function series(rows, unit, key = "value") {
    return { labels: rows.map((r) => label(r.bucket || r.day, unit)), data: rows.map((r) => Number(r[key] || 0)) };
  }
  function refreshTheme() { Object.keys(charts).forEach((k) => { charts[k].destroy(); delete charts[k]; }); }
  window.AyakaCharts = { render, series, label, refreshTheme, charts };
})();
