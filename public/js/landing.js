/* AYAKA API — Landing page: live health terminal + live DB counters */
(function () {
  "use strict";
  const { api, esc, $, $$, animateCount } = window.Ayaka;
  const PLACEHOLDER = "https://YOUR-AYAKA-DOMAIN.vercel.app";

  function personalizeCode() {
    $$("[data-code] code").forEach((c) => { c.textContent = c.textContent.split(PLACEHOLDER).join(location.origin); });
  }

  function colorJson(obj) {
    return esc(JSON.stringify(obj, null, 2))
      .replace(/(&quot;[^&]*?&quot;)(\s*:)/g, '<span class="t-key">$1</span>$2')
      .replace(/:\s(&quot;.*?&quot;)/g, ': <span class="t-str">$1</span>')
      .replace(/:\s(true|false|null|-?\d+\.?\d*)/g, ': <span class="t-num">$1</span>');
  }

  async function health() {
    const r = await api("/api/health", { handleAuth: false });
    const term = $("#hero-terminal");
    $("#hero-latency").textContent = r.status ? `${r.status} · ${r.ms}ms` : "offline";
    const body = r.json || { success: false, message: "Server tidak dapat dihubungi" };
    term.innerHTML = `<span class="t-dim">$</span> curl <span class="t-str">${esc(location.origin)}</span>/api/health\n\n${colorJson(body)}`;
  }

  async function stats() {
    const r = await api("/api/stats/public", { handleAuth: false });
    if (!r.ok) return;
    $$("[data-stat]").forEach((el) => {
      el.dataset.count = r.data[el.dataset.stat] || 0;
      animateCount(el, el.dataset.count);
    });
  }

  document.addEventListener("DOMContentLoaded", () => { personalizeCode(); health(); stats(); });
})();
