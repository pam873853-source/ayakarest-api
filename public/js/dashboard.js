/* AYAKA API — Dashboard shell: routing, sidebar, live polling, notifications and the
   Overview / Docs / Premium / Logs / Webhooks / Account / Security views. */
(function () {
  "use strict";
  const A = window.Ayaka;
  const { api, $, $$, esc, toast, fmtNum, fmtDate, timeAgo, setLoading, confirmDialog, modal, animateCount, copyText } = A;
  const TITLES = { overview: "Overview", keys: "API Key Manager", docs: "API Documentation", playground: "API Playground",
    premium: "Magic Link Premium", analytics: "Analytics", logs: "Request Logs", webhooks: "Webhook Settings",
    account: "Account Settings", security: "Security", help: "Help Center" };
  const views = {};           // name -> { load(), poll() }
  const Dash = { me: null, current: null, register(name, v) { views[name] = v; }, refresh };
  window.Dash = Dash;
  const POLL_MS = 4000;
  let pollTimer = null, inFlight = false;

  const statusBadge = (s) => `<span class="badge badge-${esc(s)}">${esc(s)}</span>`;
  const methodBadge = (m) => `<span class="badge m-${esc(String(m).toLowerCase())}">${esc(m)}</span>`;
  const codeClass = (c) => (c < 400 ? "ok" : "bad");
  const empty = (cols, text) => `<tr><td colspan="${cols}"><div class="empty-state"><strong>${esc(text)}</strong></div></td></tr>`;
  const errRow = (cols, r) => `<tr><td colspan="${cols}"><div class="callout danger">${esc(r.message || "Gagal memuat data")}</div></td></tr>`;
  Object.assign(Dash, { statusBadge, methodBadge, codeClass, empty, errRow });

  /* ---------------- Shell ---------------- */
  function initSidebar() {
    const shell = $("#shell");
    try { if (sessionStorage.getItem("ayaka-sb") === "collapsed") shell.classList.add("collapsed"); } catch (e) { /* ignore */ }
    $("#sb-collapse").addEventListener("click", () => {
      const c = shell.classList.toggle("collapsed");
      try { sessionStorage.setItem("ayaka-sb", c ? "collapsed" : "open"); } catch (e) { /* ignore */ }
      $("#sb-collapse").setAttribute("aria-label", c ? "Lebarkan sidebar" : "Ciutkan sidebar");
    });
    $("#sb-open").addEventListener("click", () => shell.classList.add("mobile-open"));
    $$("[data-sb-close]").forEach((el) => el.addEventListener("click", () => shell.classList.remove("mobile-open")));
    $$(".sb-link[data-nav]").forEach((a) => a.addEventListener("click", () => shell.classList.remove("mobile-open")));
    $$("[data-logout]").forEach((b) => b.addEventListener("click", logout));
  }

  async function logout() {
    const ok = await confirmDialog({ title: "Logout?", body: "Sesi Anda di perangkat ini akan diakhiri.", confirmText: "Logout" });
    if (!ok) return;
    await api("/api/auth/logout", { method: "POST", handleAuth: false });
    location.href = "/login";
  }

  function route() {
    let name = (location.hash || "#overview").slice(1).split("?")[0];
    if (!TITLES[name]) name = "overview";
    Dash.current = name;
    $$("[data-view]").forEach((s) => { s.hidden = s.dataset.view !== name; });
    $$("[data-nav]").forEach((a) => {
      const on = a.dataset.nav === name;
      a.classList.toggle("active", on);
      if (on) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
    });
    $("#view-title").textContent = TITLES[name];
    document.title = `${TITLES[name]} — AYAKA API`;
    window.scrollTo({ top: 0 });
    const v = views[name];
    if (v && v.load) v.load();
    schedulePoll();
  }

  /* ---------------- Live polling ---------------- */
  function setLive(paused) {
    $("#live").classList.toggle("paused", paused);
    $("#live").title = paused ? "Polling dijeda (tab tidak aktif)" : "Data diperbarui otomatis setiap 4 detik";
  }
  function stamp() {
    const t = new Date().toLocaleTimeString("id-ID");
    $("#last-update").textContent = t;
    const an = $("#an-updated"); if (an) an.textContent = t;
  }
  async function tick() {
    if (document.hidden || inFlight) return;
    const v = views[Dash.current];
    inFlight = true;
    try {
      await Promise.all([v && v.poll ? v.poll() : null, loadNotifications(true)]);
      stamp();
    } finally { inFlight = false; }
  }
  function schedulePoll() {
    clearInterval(pollTimer);
    if (document.hidden) { setLive(true); return; }
    setLive(false);
    pollTimer = setInterval(tick, POLL_MS);
  }
  function refresh() { const v = views[Dash.current]; if (v && v.load) v.load(); }
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) { clearInterval(pollTimer); setLive(true); } else { tick(); schedulePoll(); }
  });

  /* ---------------- Notifications ---------------- */
  let notifCount = -1;
  async function loadNotifications(quiet) {
    const r = await api("/api/notifications");
    if (!r.ok) return;
    const n = r.data.unread;
    const dot = $("#bell-dot");
    dot.textContent = n > 99 ? "99+" : n;
    dot.classList.toggle("hidden", !n);
    if (quiet && notifCount >= 0 && n > notifCount && r.data.items[0]) toast(r.data.items[0].title, r.data.items[0].kind === "security" ? "error" : "info");
    notifCount = n;
    const items = r.data.items.map((x) => `<div class="notif-item ${x.read_at ? "" : "unread"} ${esc(x.kind)}" data-id="${esc(x.id)}">
      <strong>${esc(x.title)}</strong>${x.body ? `<span>${esc(x.body)}</span>` : ""}<time datetime="${esc(x.created_at)}">${esc(timeAgo(x.created_at))}</time></div>`);
    const ann = r.data.announcements.map((a) => `<div class="notif-item warning"><strong>📢 ${esc(a.title)}</strong><span>${esc(a.body)}</span><time>${esc(fmtDate(a.created_at))}</time></div>`);
    $("#notif-list").innerHTML = ann.concat(items).join("") || `<div class="empty-state" style="padding:24px"><strong>Belum ada notifikasi</strong></div>`;
    Dash.notifications = r.data.items;
    if (Dash.current === "security") renderSecurityEvents();
  }
  function initNotifications() {
    const panel = $("#notif-panel"), bell = $("#bell");
    const toggle = (open) => { panel.classList.toggle("hidden", !open); bell.setAttribute("aria-expanded", open ? "true" : "false"); if (open) loadNotifications(false); };
    bell.addEventListener("click", (e) => { e.stopPropagation(); toggle(panel.classList.contains("hidden")); });
    $("#notif-close").addEventListener("click", () => toggle(false));
    document.addEventListener("click", (e) => { if (!panel.contains(e.target) && e.target !== bell) toggle(false); });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") toggle(false); });
    $("#notif-list").addEventListener("click", async (e) => {
      const it = e.target.closest(".notif-item.unread[data-id]");
      if (!it) return;
      await api(`/api/notifications/${it.dataset.id}/read`, { method: "POST" });
      loadNotifications(false);
    });
    $("#notif-readall").addEventListener("click", async () => {
      const r = await api("/api/notifications/read-all", { method: "POST" });
      if (r.ok) { toast(r.message, "success"); loadNotifications(false); }
    });
  }

  /* ---------------- Overview ---------------- */
  function hourChart(rows) {
    if (!window.AyakaCharts) return;
    const s = AyakaCharts.series(rows, "hour");
    AyakaCharts.render("ov-chart", "bar", s.labels, [{ label: "Request", data: s.data }]);
  }
  async function loadOverview() {
    const [an, usage, logs] = await Promise.all([api("/api/analytics"), api("/api/user/usage"), api("/api/logs?per_page=5")]);
    if (an.ok) {
      $$("[data-kpi]").forEach((el) => animateCount(el, an.data.totals[el.dataset.kpi] || 0));
      hourChart(an.data.charts.requests_per_hour);
    }
    if (usage.ok) {
      const u = usage.data, pct = u.monthly_quota ? Math.min(100, (100 * u.used_this_month) / u.monthly_quota) : 0;
      $("#quota-used").textContent = `${fmtNum(u.used_this_month)} request`;
      $("#quota-total").textContent = `dari ${fmtNum(u.monthly_quota)}`;
      $("#quota-bar").style.width = pct + "%";
      $("#quota-bar").style.background = pct > 90 ? "var(--red)" : pct > 70 ? "var(--yellow)" : "var(--green)";
      $("#quota-left").textContent = `Sisa ${fmtNum(u.remaining)} request (dihitung dari request ber-API Key). Reset setiap awal bulan.`;
    }
    if (logs.ok) {
      $("#ov-recent").innerHTML = logs.data.items.map((l) => `<li><span class="row" style="gap:8px;min-width:0">${methodBadge(l.method)}<code class="mono small" style="overflow:hidden;text-overflow:ellipsis">${esc(l.endpoint)}</code></span>
        <span class="row" style="gap:8px"><span class="status-pill ${codeClass(l.status_code)}">${l.status_code}</span><span class="small muted">${esc(timeAgo(l.created_at))}</span></span></li>`).join("")
        || `<li class="muted">Belum ada request. Coba kirim request dari Playground.</li>`;
    }
  }
  Dash.register("overview", { load: loadOverview, poll: loadOverview });

  /* ---------------- Docs (in-dashboard) ---------------- */
  let docsRows = [];
  async function loadDocs() {
    if (!docsRows.length) {
      const r = await api("/api/docs");
      if (!r.ok) { $("#docs-rows").innerHTML = errRow(5, r); return; }
      docsRows = r.data.endpoints;
    }
    const q = ($("#docs-filter").value || "").toLowerCase();
    const rows = docsRows.filter((e) => !q || JSON.stringify(e).toLowerCase().includes(q));
    $("#docs-rows").innerHTML = rows.map((e) => `<tr><td>${methodBadge(e.method)}</td><td><code>${esc(e.path)}</code></td><td>${esc(e.auth)}</td><td>${e.permission ? `<code>${esc(e.permission)}</code>` : "—"}</td><td>${esc(e.description)}</td></tr>`).join("") || empty(5, "Tidak ada endpoint yang cocok");
  }
  Dash.register("docs", { load: loadDocs });

  /* ---------------- Premium ---------------- */
  const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;
  let subPage = 1, subTimer;
  async function loadSubs() {
    const q = $("#sub-q").value.trim();
    const r = await api(`/api/premium/subscriptions?page=${subPage}&per_page=10${q ? "&q=" + encodeURIComponent(q) : ""}`);
    if (!r.ok) { $("#sub-rows").innerHTML = errRow(6, r); return; }
    const d = r.data;
    $("#sub-rows").innerHTML = d.items.map((s) => `<tr><td><strong>${esc(s.email)}</strong></td><td>${esc(s.plan || "—")}</td><td>${statusBadge(s.status)}</td>
      <td>${esc(fmtDate(s.activated_at))}</td><td>${esc(fmtDate(s.expires_at))}</td>
      <td><div class="key-row-actions"><button class="btn btn-sm" data-renew="${esc(s.email)}" data-icon="refresh">Renew</button>${s.status !== "revoked" ? `<button class="btn btn-sm btn-danger" data-revoke-premium="${esc(s.email)}" data-icon="x">Revoke</button>` : ""}</div></td></tr>`).join("")
      || empty(6, "Belum ada pengguna Premium. Kirim Magic Link pertama Anda.");
    A.hydrateIcons($("#sub-rows"));
    pager($("#sub-pager"), subPage, Math.max(1, Math.ceil(d.total / d.per_page)), (p) => { subPage = p; loadSubs(); });
  }
  async function loadPremiumHistory() {
    const r = await api("/api/premium/history");
    if (!r.ok) { $("#ml-history").innerHTML = errRow(4, r); return; }
    const rows = r.data.links.map((l) => ({ t: l.created_at, email: l.email, action: "magic_link", detail: `${l.plan} · ${l.duration_days} hari · email ${l.email_status}${l.used_at ? " · digunakan " + fmtDate(l.used_at) : ""}` }))
      .concat(r.data.events.map((e) => ({ t: e.created_at, email: e.email, action: e.action, detail: `${e.duration_days ? "+" + e.duration_days + " hari · " : ""}oleh ${e.actor_type}${e.new_expires_at ? " · s/d " + fmtDate(e.new_expires_at) : ""}` })))
      .sort((a, b) => new Date(b.t) - new Date(a.t)).slice(0, 60);
    $("#ml-history").innerHTML = rows.map((x) => `<tr><td class="small">${esc(fmtDate(x.t))}</td><td>${esc(x.email)}</td><td><span class="tag">${esc(x.action)}</span></td><td class="small">${esc(x.detail)}</td></tr>`).join("") || empty(4, "Belum ada riwayat");
  }
  function loadPremium() { loadSubs(); loadPremiumHistory(); }
  function initPremium() {
    $("#ml-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const email = $("#ml-email").value.trim();
      $("#ml-email-err").textContent = EMAIL_RE.test(email) ? "" : "Format email tidak valid";
      if (!EMAIL_RE.test(email)) return;
      const btn = e.submitter || $("#ml-form [type=submit]");
      setLoading(btn, true);
      const body = { email, plan: $("#ml-plan").value };
      if ($("#ml-name").value.trim()) body.name = $("#ml-name").value.trim();
      const r = await api("/api/am/send", { method: "POST", body });
      setLoading(btn, false);
      if (!r.ok) return toast(`${r.message}${r.code ? " (" + r.code + ")" : ""}`, "error", 6000);
      toast(`Magic Link terkirim ke ${email}. Berlaku ${Math.round(r.data.expires_in / 60)} menit.`, "success");
      $("#ml-form").reset();
      loadPremium();
    });
    $("#ml-status-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const email = $("#ml-status-email").value.trim();
      if (!EMAIL_RE.test(email)) return toast("Format email tidak valid", "error");
      const r = await api("/api/am/status?email=" + encodeURIComponent(email));
      const out = $("#ml-status-out");
      if (!r.ok) return toast(r.message, "error");
      const d = r.data;
      out.innerHTML = `<dt>Status</dt><dd>${statusBadge(d.status)}</dd><dt>Premium</dt><dd>${d.premium ? "Ya" : "Tidak"}</dd><dt>Plan</dt><dd>${esc(d.plan || "—")}</dd><dt>Aktif sejak</dt><dd>${esc(fmtDate(d.activated_at))}</dd><dt>Kedaluwarsa</dt><dd>${esc(fmtDate(d.expires_at))}</dd>`;
      out.classList.remove("hidden");
    });
    $("#sub-q").addEventListener("input", () => { clearTimeout(subTimer); subTimer = setTimeout(() => { subPage = 1; loadSubs(); }, 300); });
    $("#sub-rows").addEventListener("click", async (e) => {
      const rn = e.target.closest("[data-renew]"), rv = e.target.closest("[data-revoke-premium]");
      if (rn) {
        const email = rn.dataset.renew;
        modal(`<h3>Renew Premium</h3><p class="muted">${esc(email)}</p><form id="renew-f"><div class="field"><label for="renew-days">Tambah durasi (hari)</label><input class="input" id="renew-days" type="number" min="1" max="365" value="30" required></div>
          <div class="row" style="justify-content:flex-end"><button class="btn" type="button" data-close>Batal</button><button class="btn btn-primary" type="submit">Renew</button></div></form>`, {
          onMount(m, close) {
            m.querySelector("#renew-f").addEventListener("submit", async (ev) => {
              ev.preventDefault();
              const days = parseInt(m.querySelector("#renew-days").value, 10);
              if (!(days >= 1 && days <= 365)) return toast("Durasi 1–365 hari", "error");
              const r = await api("/api/am/renew", { method: "POST", body: { email, duration_days: days } });
              if (!r.ok) return toast(r.message, "error");
              close(); toast(`Premium ${email} diperpanjang s/d ${fmtDate(r.data.expires_at)}`, "success"); loadPremium();
            });
          } });
      }
      if (rv) {
        const email = rv.dataset.revokePremium;
        const ok = await confirmDialog({ title: "Cabut Premium?", body: `Premium untuk <strong>${esc(email)}</strong> akan dicabut seketika dan pengguna menerima email pemberitahuan.`, confirmText: "Revoke Premium", danger: true });
        if (!ok) return;
        const r = await api("/api/am/revoke", { method: "POST", body: { email, reason: "Dicabut dari dashboard" } });
        if (!r.ok) return toast(r.message, "error");
        toast("Premium dicabut", "success"); loadPremium();
      }
    });
  }
  Dash.register("premium", { load: loadPremium });

  /* ---------------- Logs ---------------- */
  let logPage = 1;
  function logParams() {
    const p = new URLSearchParams();
    new FormData($("#log-filter")).forEach((v, k) => { if (String(v).trim()) p.set(k, String(v).trim()); });
    return p;
  }
  async function loadLogs() {
    const p = logParams();
    $("#log-export").href = "/api/logs/export.csv" + (p.toString() ? "?" + p : "");
    p.set("page", logPage); p.set("per_page", 20);
    const r = await api("/api/logs?" + p);
    if (!r.ok) { $("#log-rows").innerHTML = errRow(8, r); return; }
    $("#log-rows").innerHTML = r.data.items.map((l) => `<tr><td class="small">${esc(fmtDate(l.created_at))}</td><td>${methodBadge(l.method)}</td><td><code class="small">${esc(l.endpoint)}</code></td>
      <td><span class="status-pill ${codeClass(l.status_code)}">${l.status_code}</span>${l.error_code ? `<div class="small muted">${esc(l.error_code)}</div>` : ""}</td><td class="mono small">${l.response_time_ms} ms</td>
      <td class="small">${esc(l.api_key_name || (l.auth_type === "session" ? "Dashboard" : "—"))}</td><td class="mono small">${esc(l.ip_masked || "—")}</td>
      <td><button class="btn btn-sm" data-log="${esc(l.request_id)}">Detail</button></td></tr>`).join("") || empty(8, "Tidak ada log yang cocok dengan filter");
    pager($("#log-pager"), logPage, r.data.pages, (pg) => { logPage = pg; loadLogs(); }, r.data.total);
  }
  function initLogs() {
    $("#log-filter").addEventListener("submit", (e) => { e.preventDefault(); logPage = 1; loadLogs(); });
    $("#log-filter").addEventListener("reset", () => setTimeout(() => { logPage = 1; loadLogs(); }, 0));
    $("#log-rows").addEventListener("click", async (e) => {
      const b = e.target.closest("[data-log]");
      if (!b) return;
      const r = await api("/api/logs/" + encodeURIComponent(b.dataset.log));
      if (!r.ok) return toast(r.message, "error");
      const l = r.data;
      modal(`<h3>Detail request</h3><dl class="kv">
        <dt>Request ID</dt><dd class="mono">${esc(l.request_id)}</dd><dt>Waktu</dt><dd>${esc(fmtDate(l.created_at))}</dd>
        <dt>Endpoint</dt><dd>${methodBadge(l.method)} <code>${esc(l.endpoint)}</code></dd><dt>Status</dt><dd><span class="status-pill ${codeClass(l.status_code)}">${l.status_code}</span> ${esc(l.error_code || "")}</dd>
        <dt>Durasi</dt><dd>${l.response_time_ms} ms</dd><dt>Autentikasi</dt><dd>${esc(l.auth_type || "—")}</dd><dt>API Key</dt><dd>${esc(l.api_key_name || "—")}</dd>
        <dt>IP (masked)</dt><dd class="mono">${esc(l.ip_masked || "—")}</dd><dt>User-Agent</dt><dd class="small">${esc(l.user_agent || "—")}</dd></dl>
        <div class="row" style="justify-content:flex-end;margin-top:16px"><button class="btn" data-close>Tutup</button></div>`);
    });
  }
  async function loadKeyOptions() {
    const r = await api("/api/keys");
    if (!r.ok) return;
    const sel = $("#lf-key"), cur = sel.value;
    sel.innerHTML = `<option value="">Semua</option>` + r.data.items.map((k) => `<option value="${esc(k.id)}">${esc(k.name)}</option>`).join("");
    sel.value = cur;
  }
  Dash.register("logs", { load() { loadKeyOptions(); loadLogs(); }, poll: () => (logPage === 1 ? loadLogs() : null) });

  function pager(el, page, pages, go, total) {
    el.innerHTML = `${total !== undefined ? `<span class="small muted">${fmtNum(total)} entri</span>` : ""}<button class="btn btn-sm" ${page <= 1 ? "disabled" : ""} data-p="${page - 1}">← Prev</button><span>Hal. ${page} / ${pages}</span><button class="btn btn-sm" ${page >= pages ? "disabled" : ""} data-p="${page + 1}">Next →</button>`;
    el.querySelectorAll("[data-p]").forEach((b) => b.addEventListener("click", () => go(parseInt(b.dataset.p, 10))));
  }
  Dash.pager = pager;

  /* ---------------- Webhooks ---------------- */
  let whEvents = [];
  async function loadWebhooks() {
    const r = await api("/api/webhooks");
    if (!r.ok) { $("#wh-rows").innerHTML = errRow(5, r); return; }
    if (!whEvents.length) {
      whEvents = r.data.available_events;
      $("#wh-events").innerHTML = whEvents.map((ev) => `<label class="check"><input type="checkbox" value="${esc(ev)}" checked> ${esc(ev)}</label>`).join("");
    }
    $("#wh-rows").innerHTML = r.data.items.map((h) => `<tr><td><code class="small" style="word-break:break-all">${esc(h.url)}</code></td><td class="small">${h.events.map(esc).join(", ")}</td>
      <td>${h.is_active ? statusBadge("active") : '<span class="badge badge-none">nonaktif</span>'}${h.failure_count ? `<div class="small muted">${h.failure_count}× gagal</div>` : ""}</td>
      <td class="small">${h.last_delivery_at ? `${esc(fmtDate(h.last_delivery_at))}<br>HTTP ${esc(h.last_status_code || "—")}` : "Belum pernah"}</td>
      <td><div class="key-row-actions"><button class="btn btn-sm" data-wh-test="${esc(h.id)}" data-icon="bolt">Test</button><button class="btn btn-sm" data-wh-toggle="${esc(h.id)}" data-active="${h.is_active}">${h.is_active ? "Nonaktifkan" : "Aktifkan"}</button><button class="btn btn-sm btn-danger" data-wh-del="${esc(h.id)}" data-icon="trash" aria-label="Hapus"></button></div></td></tr>`).join("")
      || empty(5, "Belum ada webhook");
    A.hydrateIcons($("#wh-rows"));
  }
  function initWebhooks() {
    $("#wh-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const url = $("#wh-url").value.trim();
      const events = $$("#wh-events input:checked").map((i) => i.value);
      $("#wh-url-err").textContent = /^https:\/\/[^\s]+$/.test(url) ? "" : "URL harus diawali https://";
      if (!/^https:\/\/[^\s]+$/.test(url)) return;
      if (!events.length) return toast("Pilih minimal satu event", "error");
      const r = await api("/api/webhooks", { method: "POST", body: { url, events } });
      if (!r.ok) return toast(r.message, "error", 6000);
      $("#wh-form").reset(); $$("#wh-events input").forEach((i) => { i.checked = true; });
      modal(`<h3>Webhook dibuat</h3><p class="muted">Simpan signing secret ini di server Anda sebagai <code class="inline">AYAKA_WEBHOOK_SECRET</code>. Secret <strong>tidak akan ditampilkan lagi</strong>.</p>
        <div class="key-secret"><code id="wh-secret">${esc(r.data.signing_secret)}</code><button class="btn" data-copy="#wh-secret" data-icon="copy">Copy</button></div>
        <div class="row" style="justify-content:flex-end;margin-top:16px"><button class="btn btn-primary" data-close>Sudah saya simpan</button></div>`, {
        dismissable: false, onMount(m) { A.initTabs(m); } });
      loadWebhooks();
    });
    $("#wh-rows").addEventListener("click", async (e) => {
      const t = e.target.closest("[data-wh-test]"), g = e.target.closest("[data-wh-toggle]"), d = e.target.closest("[data-wh-del]");
      if (t) {
        setLoading(t, true);
        const r = await api(`/api/webhooks/${t.dataset.whTest}/test`, { method: "POST" });
        setLoading(t, false);
        toast(r.ok && r.data.delivered ? `Terkirim (HTTP ${r.data.status_code})` : `Gagal: ${(r.data && r.data.error) || r.message}`, r.ok && r.data.delivered ? "success" : "error", 6000);
        loadWebhooks();
      }
      if (g) {
        const r = await api(`/api/webhooks/${g.dataset.whToggle}`, { method: "PATCH", body: { is_active: g.dataset.active !== "true" } });
        if (!r.ok) return toast(r.message, "error");
        loadWebhooks();
      }
      if (d) {
        const ok = await confirmDialog({ title: "Hapus webhook?", body: "Pengiriman event ke URL ini akan dihentikan.", confirmText: "Hapus", danger: true });
        if (!ok) return;
        const r = await api(`/api/webhooks/${d.dataset.whDel}`, { method: "DELETE" });
        if (!r.ok) return toast(r.message, "error");
        toast("Webhook dihapus", "success"); loadWebhooks();
      }
    });
  }
  Dash.register("webhooks", { load: loadWebhooks });

  /* ---------------- Account ---------------- */
  function fillAccount() {
    const u = Dash.me.user;
    $("#pf-username").value = u.username; $("#pf-name").value = u.full_name; $("#pf-email").value = u.email;
    $("#acct-info").innerHTML = `<dt>User ID</dt><dd class="mono small">${esc(u.id)}</dd><dt>Status</dt><dd>${statusBadge(u.status)}</dd><dt>Role</dt><dd>${Dash.me.is_admin ? esc(Dash.me.admin_role) : "user"}</dd>
      <dt>Terdaftar</dt><dd>${esc(fmtDate(u.created_at))}</dd><dt>Login terakhir</dt><dd>${esc(fmtDate(u.last_login_at))}</dd><dt>Kuota bulanan</dt><dd>${fmtNum(u.monthly_quota)} request</dd>
      <dt>Sesi berakhir</dt><dd>${esc(fmtDate(Dash.me.session_expires_at))}${Dash.me.remember_me ? " (Remember Me)" : ""}</dd>`;
  }
  function initAccount() {
    $("#profile-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const full_name = $("#pf-name").value.trim();
      if (full_name.length < 2) return toast("Nama lengkap wajib diisi", "error");
      const btn = $("#profile-form [type=submit]");
      setLoading(btn, true);
      const r = await api("/api/user/profile", { method: "PATCH", body: { full_name } });
      setLoading(btn, false);
      if (!r.ok) return toast(r.message, "error");
      Dash.me.user = Object.assign(Dash.me.user, r.data);
      paintUser(); toast("Profil disimpan", "success");
    });
  }
  Dash.register("account", { load: fillAccount });

  /* ---------------- Security ---------------- */
  async function loadSessions() {
    const r = await api("/api/user/sessions");
    if (!r.ok) { $("#sess-list").innerHTML = `<li class="callout danger">${esc(r.message)}</li>`; return; }
    $("#sess-list").innerHTML = r.data.items.map((s) => `<li><div style="min-width:0"><strong>${s.current ? "Perangkat ini" : esc((s.user_agent || "Perangkat tidak dikenal").slice(0, 60))}</strong>
      <div class="small muted">${esc(s.ip_masked || "")} · aktif ${esc(timeAgo(s.last_seen_at))} · berakhir ${esc(fmtDate(s.expires_at))}</div></div>
      ${s.current ? '<span class="tag tag-yellow">Sesi ini</span>' : `<button class="btn btn-sm btn-danger" data-sess="${esc(s.id)}">Keluarkan</button>`}</li>`).join("");
  }
  function renderSecurityEvents() {
    const items = (Dash.notifications || []).filter((n) => n.kind === "security");
    $("#sec-events").innerHTML = items.map((n) => `<li><span><strong>${esc(n.title)}</strong><br><span class="small muted">${esc(n.body || "")}</span></span><span class="small muted">${esc(fmtDate(n.created_at))}</span></li>`).join("")
      || `<li class="muted">Belum ada aktivitas keamanan.</li>`;
  }
  function initSecurity() {
    $("#sess-list").addEventListener("click", async (e) => {
      const b = e.target.closest("[data-sess]");
      if (!b) return;
      const r = await api(`/api/user/sessions/${b.dataset.sess}`, { method: "DELETE" });
      if (!r.ok) return toast(r.message, "error");
      toast("Sesi dikeluarkan", "success"); loadSessions();
    });
    $("#pw-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const cur = $("#pw-current").value, nw = $("#pw-new").value, cf = $("#pw-confirm").value;
      const err = !cur ? "Password saat ini wajib diisi" : (nw.length < 8 || !/[a-z]/.test(nw) || !/[A-Z]/.test(nw) || !/\d/.test(nw)) ? "Password baru belum memenuhi syarat" : nw !== cf ? "Konfirmasi password tidak sama" : "";
      $("#pw-err").textContent = err;
      if (err) return;
      const btn = $("#pw-form [type=submit]");
      setLoading(btn, true);
      const r = await api("/api/user/change-password", { method: "POST", body: { current_password: cur, new_password: nw, confirm_password: cf } });
      setLoading(btn, false);
      if (!r.ok) { $("#pw-err").textContent = r.message; return toast(r.message, "error"); }
      $("#pw-form").reset(); toast("Password diubah. Sesi lain telah dikeluarkan.", "success"); loadSessions();
    });
  }
  Dash.register("security", { load() { loadSessions(); renderSecurityEvents(); } });
  Dash.register("help", {});

  /* ---------------- Boot ---------------- */
  function paintUser() {
    const u = Dash.me.user;
    $("#sb-name").textContent = u.full_name; $("#sb-email").textContent = u.email;
    $("#sb-avatar").textContent = (u.full_name || u.username || "A").trim().charAt(0).toUpperCase();
    $("#ov-name").textContent = u.full_name.split(" ")[0];
    $("#sb-admin").classList.toggle("hidden", !Dash.me.is_admin);
  }
  document.addEventListener("DOMContentLoaded", async () => {
    initSidebar(); initNotifications(); initPremium(); initLogs(); initWebhooks(); initAccount(); initSecurity();
    $("#docs-filter").addEventListener("input", loadDocs);
    $$("[data-theme-toggle]").forEach((b) => b.addEventListener("click", () => { if (window.AyakaCharts) { AyakaCharts.refreshTheme(); setTimeout(refresh, 50); } }));
    const me = await api("/api/auth/me");
    if (!me.ok) return; // api() redirects to /login on 401
    Dash.me = me.data;
    paintUser();
    if (new URLSearchParams(location.search).get("denied") === "admin") toast("Halaman admin hanya untuk administrator.", "error");
    window.addEventListener("hashchange", route);
    route();
    loadNotifications(false);
    stamp();
  });
})();
