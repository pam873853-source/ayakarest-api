/* AYAKA API — Admin panel (all data from /api/admin/*; access enforced server-side by admin_users role) */
(function () {
  "use strict";
  const A = window.Ayaka;
  const { api, $, $$, esc, toast, fmtNum, fmtDate, timeAgo, modal, confirmDialog, animateCount, setLoading } = A;
  const TITLES = { overview: "Overview", users: "Users", keys: "API Keys", logs: "Request Logs", audit: "Audit Logs",
    monitoring: "Monitoring", settings: "Settings & Maintenance", announcements: "Pengumuman" };
  let current = "overview", pollTimer = null, me = null;
  const st = { users: 1, keys: 1, logs: 1, audit: 1 };
  const badge = (s) => `<span class="badge badge-${esc(s)}">${esc(s)}</span>`;
  const mBadge = (m) => `<span class="badge m-${esc(String(m).toLowerCase())}">${esc(m)}</span>`;
  const pill = (c) => `<span class="status-pill ${c < 400 ? "ok" : "bad"}">${c}</span>`;
  const empty = (n, t) => `<tr><td colspan="${n}"><div class="empty-state"><strong>${esc(t)}</strong></div></td></tr>`;
  const errRow = (n, r) => `<tr><td colspan="${n}"><div class="callout danger">${esc(r.message)}</div></td></tr>`;

  function pager(el, page, pages, total, go) {
    el.innerHTML = `<span class="small muted">${fmtNum(total)} entri</span><button class="btn btn-sm" ${page <= 1 ? "disabled" : ""} data-p="${page - 1}">← Prev</button><span>Hal. ${page} / ${pages}</span><button class="btn btn-sm" ${page >= pages ? "disabled" : ""} data-p="${page + 1}">Next →</button>`;
    el.querySelectorAll("[data-p]").forEach((b) => b.addEventListener("click", () => go(parseInt(b.dataset.p, 10))));
  }
  function stamp() { $("#last-update").textContent = new Date().toLocaleTimeString("id-ID"); }

  /* Overview */
  async function overview() {
    const [o, an] = await Promise.all([api("/api/admin/overview"), api("/api/admin/analytics")]);
    if (o.ok) {
      $$("[data-ak]").forEach((el) => animateCount(el, o.data.totals[el.dataset.ak] || 0));
      $("#mt-flag").classList.toggle("hidden", !o.data.maintenance.active);
    }
    if (an.ok && window.AyakaCharts) {
      const C = AyakaCharts, ch = an.data.charts;
      const r = C.series(ch.requests_per_hour, "hour");
      C.render("ad-req", "line", r.labels, [{ label: "Request", data: r.data, backgroundColor: "rgba(255,214,0,.45)" }]);
      C.render("ad-sf", "bar", ch.success_vs_failed.map((x) => C.label(x.bucket, "day")), [
        { label: "Berhasil", data: ch.success_vs_failed.map((x) => x.success), backgroundColor: "#3DDC84" },
        { label: "Gagal", data: ch.success_vs_failed.map((x) => x.failed), backgroundColor: "#FF5A5A" }], { stacked: true });
      const v = C.series(ch.visitors_per_day, "day"); C.render("ad-vis", "line", v.labels, [{ label: "Visitor", data: v.data, backgroundColor: "rgba(255,158,205,.45)" }]);
      const k = C.series(ch.keys_generated_per_day, "day"); C.render("ad-keys", "bar", k.labels, [{ label: "Key", data: k.data, backgroundColor: "#7CC4FF" }]);
      const p = C.series(ch.premium_activations_per_day, "day"); C.render("ad-prem", "bar", p.labels, [{ label: "Aktivasi", data: p.data }]);
    }
  }

  /* Users */
  async function users() {
    const q = $("#u-q").value.trim(), s = $("#u-status").value;
    const r = await api(`/api/admin/users?page=${st.users}&per_page=20${q ? "&q=" + encodeURIComponent(q) : ""}${s ? "&status=" + s : ""}`);
    if (!r.ok) { $("#u-rows").innerHTML = errRow(8, r); return; }
    $("#u-rows").innerHTML = r.data.items.map((u) => `<tr><td><strong>${esc(u.full_name)}</strong><div class="small muted">@${esc(u.username)} · ${esc(u.email)}</div></td>
      <td><span class="badge ${u.status === "active" ? "badge-active" : "badge-revoked"}">${esc(u.status)}</span></td><td>${u.admin_role ? `<span class="tag tag-dark">${esc(u.admin_role)}</span>` : "user"}</td>
      <td class="mono">${fmtNum(u.key_count)}</td><td class="mono">${fmtNum(u.request_count)}</td><td class="small">${esc(fmtDate(u.created_at, false))}</td><td class="small">${esc(timeAgo(u.last_login_at))}</td>
      <td><div class="key-row-actions"><button class="btn btn-sm" data-u-detail="${esc(u.id)}">Detail</button>
      ${u.id === me.user.id ? "" : u.status === "active" ? `<button class="btn btn-sm" data-u-suspend="${esc(u.id)}" data-email="${esc(u.email)}">Suspend</button>` : `<button class="btn btn-sm" data-u-activate="${esc(u.id)}">Activate</button>`}
      ${u.id === me.user.id ? "" : `<button class="btn btn-sm btn-danger" data-u-delete="${esc(u.id)}" data-email="${esc(u.email)}" data-icon="trash" aria-label="Hapus"></button>`}</div></td></tr>`).join("") || empty(8, "Tidak ada pengguna");
    A.hydrateIcons($("#u-rows"));
    pager($("#u-pager"), st.users, r.data.pages, r.data.total, (p) => { st.users = p; users(); });
  }
  async function userDetail(id) {
    const r = await api("/api/admin/users/" + id);
    if (!r.ok) return toast(r.message, "error");
    const u = r.data;
    modal(`<h3>${esc(u.full_name)}</h3><dl class="kv">
      <dt>Email</dt><dd>${esc(u.email)}</dd><dt>Username</dt><dd>@${esc(u.username)}</dd><dt>Status</dt><dd>${esc(u.status)}</dd><dt>Role</dt><dd>${esc(u.admin_role || "user")}</dd>
      <dt>Terdaftar</dt><dd>${esc(fmtDate(u.created_at))}</dd><dt>Login terakhir</dt><dd>${esc(fmtDate(u.last_login_at))}</dd>
      <dt>Gagal login</dt><dd>${u.failed_login_count}${u.locked_until ? " · terkunci s/d " + esc(fmtDate(u.locked_until)) : ""}</dd>
      <dt>Request</dt><dd>${fmtNum(u.stats.requests)} (${fmtNum(u.stats.failed)} gagal)</dd><dt>Pelanggan Premium</dt><dd>${fmtNum(u.premium_customers)}</dd></dl>
      <form id="quota-f" class="row" style="margin:14px 0;gap:8px;align-items:end"><div class="field" style="margin:0;flex:1"><label for="q-val">Kuota bulanan</label><input class="input" id="q-val" type="number" min="0" max="100000000" value="${u.monthly_quota}"></div><button class="btn btn-primary" type="submit">Simpan kuota</button></form>
      <h4>API Key (${u.keys.length})</h4><ul class="list-plain">${u.keys.map((k) => `<li><span><strong>${esc(k.name)}</strong> <code class="small">${esc(k.masked_key)}</code></span>${badge(k.status)}</li>`).join("") || "<li class='muted'>Tidak ada</li>"}</ul>
      <h4>Aktivitas terbaru</h4><ul class="list-plain">${u.activity.map((a) => `<li><span class="tag">${esc(a.action)}</span><span class="small muted">${esc(fmtDate(a.created_at))}</span></li>`).join("") || "<li class='muted'>Tidak ada</li>"}</ul>
      <div class="row" style="justify-content:flex-end;margin-top:14px"><button class="btn" data-close>Tutup</button></div>`, {
      onMount(m) {
        m.querySelector("#quota-f").addEventListener("submit", async (e) => {
          e.preventDefault();
          const r2 = await api(`/api/admin/users/${id}/quota`, { method: "PUT", body: { monthly_quota: parseInt(m.querySelector("#q-val").value, 10) } });
          toast(r2.message, r2.ok ? "success" : "error");
        });
      } });
  }
  async function userAction(e) {
    const b = e.target.closest("button"); if (!b) return;
    if (b.dataset.uDetail) return userDetail(b.dataset.uDetail);
    if (b.dataset.uSuspend) {
      const ok = await confirmDialog({ title: "Tangguhkan pengguna?", body: `<strong>${esc(b.dataset.email)}</strong> akan dikeluarkan dari semua sesi dan seluruh API Key-nya ditolak sampai diaktifkan kembali.`, confirmText: "Suspend", danger: true });
      if (!ok) return;
      const r = await api(`/api/admin/users/${b.dataset.uSuspend}/suspend`, { method: "POST", body: { reason: "Suspended by admin" } });
      toast(r.message, r.ok ? "success" : "error"); users();
    }
    if (b.dataset.uActivate) {
      const r = await api(`/api/admin/users/${b.dataset.uActivate}/activate`, { method: "POST", body: {} });
      toast(r.message, r.ok ? "success" : "error"); users();
    }
    if (b.dataset.uDelete) {
      const email = b.dataset.email;
      const typed = await confirmDialog({ title: "Hapus pengguna permanen?", body: `Semua data <strong>${esc(email)}</strong> (API Key, premium, logs terkait) akan dihapus dan tidak bisa dikembalikan.`, confirmText: "Hapus permanen", danger: true, requireText: email });
      if (!typed) return;
      const r = await api(`/api/admin/users/${b.dataset.uDelete}`, { method: "DELETE", body: { confirm_email: typed } });
      toast(r.message, r.ok ? "success" : "error"); users();
    }
  }

  /* Keys */
  async function keys() {
    const q = $("#k-q").value.trim();
    const r = await api(`/api/admin/keys?page=${st.keys}${q ? "&q=" + encodeURIComponent(q) : ""}`);
    if (!r.ok) { $("#k-rows").innerHTML = errRow(7, r); return; }
    $("#k-rows").innerHTML = r.data.items.map((k) => `<tr><td><strong>${esc(k.name)}</strong></td><td class="small">${esc(k.owner_email)}</td><td><code class="small">${esc(k.masked_key)}</code></td>
      <td>${badge(k.status)}</td><td class="mono">${fmtNum(k.usage_count)}</td><td class="small">${esc(timeAgo(k.last_used_at))}</td>
      <td>${k.status !== "revoked" ? `<button class="btn btn-sm btn-danger" data-k-revoke="${esc(k.id)}" data-name="${esc(k.name)}">Revoke</button>` : ""}</td></tr>`).join("") || empty(7, "Tidak ada API Key");
    pager($("#k-pager"), st.keys, r.data.pages, r.data.total, (p) => { st.keys = p; keys(); });
  }
  async function keyAction(e) {
    const b = e.target.closest("[data-k-revoke]"); if (!b) return;
    const ok = await confirmDialog({ title: "Revoke API Key?", body: `Key <strong>${esc(b.dataset.name)}</strong> akan dicabut seketika. Pemilik akan menerima notifikasi.`, confirmText: "Revoke", danger: true });
    if (!ok) return;
    const r = await api(`/api/admin/keys/${b.dataset.kRevoke}/revoke`, { method: "POST", body: { reason: "Dicabut oleh administrator AYAKA Sync" } });
    toast(r.message, r.ok ? "success" : "error"); keys();
  }

  /* Logs */
  async function logs() {
    const p = new URLSearchParams({ page: st.logs, per_page: 25 });
    if ($("#l-q").value.trim()) p.set("q", $("#l-q").value.trim());
    if ($("#l-endpoint").value.trim()) p.set("endpoint", $("#l-endpoint").value.trim());
    if ($("#l-status").value) p.set("status", $("#l-status").value);
    const r = await api("/api/admin/logs?" + p);
    if (!r.ok) { $("#l-rows").innerHTML = errRow(7, r); return; }
    $("#l-rows").innerHTML = r.data.items.map((l) => `<tr><td class="small">${esc(fmtDate(l.created_at))}</td><td>${mBadge(l.method)}</td><td><code class="small">${esc(l.endpoint)}</code></td>
      <td>${pill(l.status_code)} <span class="small muted">${esc(l.error_code || "")}</span></td><td class="mono small">${l.response_time_ms} ms</td><td class="small">${esc(l.user_email || "anonim")}</td><td class="mono small">${esc(l.ip_masked || "—")}</td></tr>`).join("") || empty(7, "Belum ada log");
    pager($("#l-pager"), st.logs, r.data.pages, r.data.total, (pg) => { st.logs = pg; logs(); });
  }

  /* Audit */
  async function audit() {
    const p = new URLSearchParams({ page: st.audit });
    if ($("#a-q").value.trim()) p.set("q", $("#a-q").value.trim());
    if ($("#a-actor").value) p.set("actor_type", $("#a-actor").value);
    const r = await api("/api/admin/audit?" + p);
    if (!r.ok) { $("#a-rows").innerHTML = errRow(6, r); return; }
    $("#a-rows").innerHTML = r.data.items.map((a) => `<tr><td class="small">${esc(fmtDate(a.created_at))}</td><td><span class="tag">${esc(a.action)}</span></td><td class="small">${esc(a.actor_type)}</td>
      <td class="small">${esc(a.user_email || "—")}</td><td class="small">${esc([a.target_type, a.target_id].filter(Boolean).join(": ") || "—")}</td><td class="mono small">${esc(a.ip_masked || "—")}</td></tr>`).join("") || empty(6, "Belum ada audit log");
    pager($("#a-pager"), st.audit, r.data.pages, r.data.total, (pg) => { st.audit = pg; audit(); });
  }

  /* Monitoring */
  async function monitoring() {
    const r = await api("/api/admin/monitoring");
    if (!r.ok) { $("#mon-cards").innerHTML = `<div class="callout danger">${esc(r.message)}</div>`; return; }
    const d = r.data, dot = (s) => `<span class="health-dot ${esc(s)}"></span>`;
    $("#mon-cards").innerHTML = `
      <div class="card" style="padding:18px"><h3 style="margin-top:0">${dot(d.server.status)} Server</h3><dl class="kv"><dt>Versi</dt><dd>AYAKA API ${esc(d.server.version)}</dd><dt>Python</dt><dd>${esc(d.server.python)}</dd><dt>Environment</dt><dd>${esc(d.server.environment)}</dd><dt>Region</dt><dd>${esc(d.server.region)}</dd><dt>Uptime instance</dt><dd>${fmtNum(d.server.instance_uptime_s)} dtk</dd><dt>Base URL</dt><dd class="small">${esc(d.server.base_url || "—")}</dd></dl></div>
      <div class="card" style="padding:18px"><h3 style="margin-top:0">${dot(d.database.status)} Database</h3><dl class="kv"><dt>Status</dt><dd>${esc(d.database.status)}${d.database.latency_ms !== undefined ? " · " + d.database.latency_ms + " ms" : ""}</dd><dt>Nama</dt><dd>${esc(d.database.name || "—")}</dd><dt>Ukuran</dt><dd>${esc(d.database.size || "—")}</dd><dt>Koneksi</dt><dd>${esc(d.database.connections ?? "—")}</dd><dt>Pool</dt><dd class="small">${esc(JSON.stringify(d.database.pool || {}))}</dd><dt>Versi</dt><dd class="small">${esc((d.database.version || "").split(" on ")[0])}</dd></dl></div>
      <div class="card" style="padding:18px"><h3 style="margin-top:0">${dot(d.email.status)} Resend</h3><dl class="kv"><dt>Status</dt><dd>${esc(d.email.status)}</dd><dt>Detail</dt><dd class="small">${esc(d.email.detail || "")}</dd><dt>From</dt><dd class="small">${esc(d.email.from || "belum diatur")}</dd>
        <dt>24 jam</dt><dd>${fmtNum(d.email.last_24h.sent)} terkirim · ${fmtNum(d.email.last_24h.failed)} gagal</dd>${d.email.domains ? `<dt>Domain</dt><dd class="small">${d.email.domains.map((x) => esc(x.name + " (" + x.status + ")")).join(", ") || "—"}</dd>` : ""}${d.email.last_24h.last_error ? `<dt>Error terakhir</dt><dd class="small">${esc(d.email.last_24h.last_error)}</dd>` : ""}</dl></div>`;
    $("#mon-errors").innerHTML = d.errors_24h.map((x) => `<tr><td><code>${esc(x.endpoint)}</code></td><td>${pill(x.status_code)}</td><td>${esc(x.error_code || "—")}</td><td class="mono">${x.n}</td><td class="small">${esc(fmtDate(x.last_seen))}</td></tr>`).join("") || empty(5, "Tidak ada error 5xx dalam 24 jam");
    $("#mon-tables").innerHTML = (d.database.tables || []).map((t) => `<tr><td><code>${esc(t.table)}</code></td><td class="mono">${fmtNum(t.rows)}</td></tr>`).join("");
  }

  /* Settings */
  const toLocal = (iso) => { if (!iso) return ""; const d = new Date(iso); return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16); };
  async function settings() {
    const r = await api("/api/admin/settings");
    if (!r.ok) return toast(r.message, "error");
    const m = r.data.maintenance;
    $("#mt-enabled").checked = !!m.enabled; $("#mt-message").value = m.message || "";
    $("#mt-start").value = toLocal(m.start_at); $("#mt-end").value = toLocal(m.end_at);
    $("#mt-state").innerHTML = m.active ? '<span class="tag tag-yellow">AKTIF sekarang</span>' : m.scheduled ? `<span class="tag">Terjadwal mulai ${esc(fmtDate(m.start_at))}</span>` : '<span class="tag">Nonaktif</span>';
    $("#mt-flag").classList.toggle("hidden", !m.active);
    $("#set-reg").checked = (r.data.registration || {}).open !== false;
    $("#set-rl").value = (r.data.defaults || {}).rate_limit_per_minute || 60;
    $("#set-quota").value = (r.data.defaults || {}).monthly_quota || 10000;
  }
  function initSettings() {
    $("#mt-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const enabled = $("#mt-enabled").checked;
      if (enabled) {
        const ok = await confirmDialog({ title: "Aktifkan Maintenance Mode?", body: "Pengguna non-admin akan diarahkan ke halaman maintenance dan API publik mengembalikan 503 selama jadwal berlaku.", confirmText: "Aktifkan", danger: true });
        if (!ok) return;
      }
      const s = $("#mt-start").value, en = $("#mt-end").value;
      if (s && en && new Date(en) <= new Date(s)) return toast("Waktu selesai harus setelah waktu mulai", "error");
      const btn = $("#mt-form [type=submit]"); setLoading(btn, true);
      const r = await api("/api/admin/maintenance", { method: "PUT", body: { enabled, message: $("#mt-message").value.trim() || "AYAKA API sedang dalam pemeliharaan terjadwal.", start_at: s ? new Date(s).toISOString() : null, end_at: en ? new Date(en).toISOString() : null } });
      setLoading(btn, false);
      toast(r.message, r.ok ? "success" : "error"); settings();
    });
    $("#set-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const r = await api("/api/admin/settings", { method: "PUT", body: { registration_open: $("#set-reg").checked, default_rate_limit_per_minute: parseInt($("#set-rl").value, 10), default_monthly_quota: parseInt($("#set-quota").value, 10) } });
      toast(r.message, r.ok ? "success" : "error");
    });
  }

  /* Announcements */
  async function announcements() {
    const r = await api("/api/admin/announcements");
    if (!r.ok) return;
    $("#ann-list").innerHTML = r.data.items.map((a) => `<li><div style="min-width:0;flex:1"><span class="tag ${a.level === "critical" ? "tag-dark" : "tag-yellow"}">${esc(a.level)}</span> <strong>${esc(a.title)}</strong>${a.is_active ? "" : ' <span class="badge badge-none">nonaktif</span>'}<div class="small muted">${esc(a.body)}</div><div class="small muted">${esc(fmtDate(a.created_at))}</div></div>
      <div class="key-row-actions"><button class="btn btn-sm" data-ann-toggle="${esc(a.id)}">${a.is_active ? "Nonaktifkan" : "Aktifkan"}</button><button class="btn btn-sm btn-danger" data-ann-del="${esc(a.id)}" data-icon="trash" aria-label="Hapus"></button></div></li>`).join("") || `<li class="muted">Belum ada pengumuman.</li>`;
    A.hydrateIcons($("#ann-list"));
  }
  function initAnnouncements() {
    $("#ann-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const body = { title: $("#ann-title").value.trim(), body: $("#ann-body").value.trim(), level: $("#ann-level").value };
      if (body.title.length < 3 || body.body.length < 3) return toast("Judul dan isi minimal 3 karakter", "error");
      const r = await api("/api/admin/announcements", { method: "POST", body });
      toast(r.message, r.ok ? "success" : "error");
      if (r.ok) { $("#ann-form").reset(); announcements(); }
    });
    $("#ann-list").addEventListener("click", async (e) => {
      const t = e.target.closest("[data-ann-toggle]"), d = e.target.closest("[data-ann-del]");
      if (t) { const r = await api(`/api/admin/announcements/${t.dataset.annToggle}`, { method: "PATCH" }); toast(r.message, r.ok ? "success" : "error"); announcements(); }
      if (d) {
        if (!(await confirmDialog({ title: "Hapus pengumuman?", body: "Pengumuman akan hilang dari semua halaman.", confirmText: "Hapus", danger: true }))) return;
        const r = await api(`/api/admin/announcements/${d.dataset.annDel}`, { method: "DELETE" }); toast(r.message, r.ok ? "success" : "error"); announcements();
      }
    });
  }

  const LOADERS = { overview, users, keys, logs, audit, monitoring, settings, announcements };
  const POLL = { overview: true, logs: true };
  function route() {
    let name = (location.hash || "#overview").slice(1);
    if (!TITLES[name]) name = "overview";
    current = name;
    $$("[data-view]").forEach((s) => { s.hidden = s.dataset.view !== name; });
    $$("[data-nav]").forEach((a) => a.classList.toggle("active", a.dataset.nav === name));
    $("#view-title").textContent = TITLES[name];
    document.title = `${TITLES[name]} — Admin AYAKA API`;
    LOADERS[name]().then(stamp);
  }
  function startPolling() {
    clearInterval(pollTimer);
    $("#live").classList.toggle("paused", document.hidden);
    if (document.hidden) return;
    pollTimer = setInterval(() => { if (POLL[current] && !document.hidden) LOADERS[current]().then(stamp); }, 5000);
  }
  document.addEventListener("visibilitychange", startPolling);

  document.addEventListener("DOMContentLoaded", async () => {
    const shell = $("#shell");
    try { if (sessionStorage.getItem("ayaka-admin-sb") === "collapsed") shell.classList.add("collapsed"); } catch (e) { /* ignore */ }
    $("#sb-collapse").addEventListener("click", () => { const c = shell.classList.toggle("collapsed"); try { sessionStorage.setItem("ayaka-admin-sb", c ? "collapsed" : "open"); } catch (e) { /* ignore */ } });
    $("#sb-open").addEventListener("click", () => shell.classList.add("mobile-open"));
    $$("[data-sb-close], .sb-link[data-nav]").forEach((el) => el.addEventListener("click", () => shell.classList.remove("mobile-open")));
    $$("[data-logout]").forEach((b) => b.addEventListener("click", async () => {
      if (!(await confirmDialog({ title: "Logout?", body: "Sesi admin akan diakhiri.", confirmText: "Logout" }))) return;
      await api("/api/auth/logout", { method: "POST", handleAuth: false }); location.href = "/login";
    }));
    $("#u-filter").addEventListener("submit", (e) => { e.preventDefault(); st.users = 1; users(); });
    $("#k-filter").addEventListener("submit", (e) => { e.preventDefault(); st.keys = 1; keys(); });
    $("#l-filter").addEventListener("submit", (e) => { e.preventDefault(); st.logs = 1; logs(); });
    $("#a-filter").addEventListener("submit", (e) => { e.preventDefault(); st.audit = 1; audit(); });
    $("#u-rows").addEventListener("click", userAction);
    $("#k-rows").addEventListener("click", keyAction);
    $("#mon-refresh").addEventListener("click", monitoring);
    $$("[data-theme-toggle]").forEach((b) => b.addEventListener("click", () => { if (window.AyakaCharts) { AyakaCharts.refreshTheme(); setTimeout(() => LOADERS[current](), 50); } }));
    initSettings(); initAnnouncements();
    const r = await api("/api/auth/me");
    if (!r.ok) return;
    if (!r.data.is_admin) { location.href = "/dashboard?denied=admin"; return; }
    me = r.data;
    $("#sb-name").textContent = me.user.full_name; $("#sb-email").textContent = me.user.email;
    $("#sb-avatar").textContent = (me.user.full_name || "A").charAt(0).toUpperCase();
    $("#adm-role").textContent = me.admin_role; $("#adm-identity").textContent = `Ayaka Sync (${me.user.full_name})`;
    window.addEventListener("hashchange", route);
    route(); startPolling();
  });
})();
