/* AYAKA API — API Key Manager: generate (shown once), list, detail, edit, regenerate, revoke */
(function () {
  "use strict";
  const A = window.Ayaka, Dash = window.Dash;
  const { api, $, $$, esc, toast, fmtDate, timeAgo, fmtNum, modal, confirmDialog, setLoading } = A;
  let PERMS = null, filter = "";

  async function perms() {
    if (PERMS) return PERMS;
    const r = await api("/api/keys/permissions");
    PERMS = r.ok ? r.data.permissions : {};
    return PERMS;
  }
  function permGrid(selected) {
    return `<div class="perm-grid">${Object.entries(PERMS).map(([k, d]) => `<label class="check"><input type="checkbox" name="perm" value="${esc(k)}" ${selected.includes(k) ? "checked" : ""}> <code>${esc(k)}</code><small>${esc(d)}</small></label>`).join("")}</div>`;
  }

  async function load() {
    const r = await api("/api/keys" + (filter ? "?status=" + filter : ""));
    if (!r.ok) { $("#key-rows").innerHTML = Dash.errRow(8, r); return; }
    const c = r.data.counts || {};
    $("#key-counts").textContent = `${fmtNum(c.active || 0)} active · ${fmtNum(c.expired || 0)} expired · ${fmtNum(c.revoked || 0)} revoked`;
    $("#key-rows").innerHTML = r.data.items.map((k) => `<tr>
      <td><strong>${esc(k.name)}</strong>${k.description ? `<div class="small muted">${esc(k.description)}</div>` : ""}</td>
      <td><code class="small">${esc(k.masked_key)}</code></td>
      <td>${Dash.statusBadge(k.status)}</td>
      <td class="small">${k.permissions.map((p) => `<code>${esc(p)}</code>`).join(" ")}</td>
      <td class="mono">${fmtNum(k.usage_count)}</td>
      <td class="small">${esc(timeAgo(k.last_used_at))}</td>
      <td class="small">${k.expires_at ? esc(fmtDate(k.expires_at, false)) : "Tidak ada"}</td>
      <td><div class="key-row-actions">
        <button class="btn btn-sm" data-k-detail="${esc(k.id)}">Detail</button>
        ${k.status !== "revoked" ? `<button class="btn btn-sm" data-k-edit="${esc(k.id)}">Edit</button><button class="btn btn-sm" data-k-regen="${esc(k.id)}" data-icon="sync">Regenerate</button><button class="btn btn-sm btn-danger" data-k-revoke="${esc(k.id)}" data-name="${esc(k.name)}">Revoke</button>` : ""}
      </div></td></tr>`).join("") || Dash.empty(8, filter ? "Tidak ada key dengan status ini" : "Belum ada API Key. Klik Generate API Key untuk membuat yang pertama.");
    A.hydrateIcons($("#key-rows"));
    window.__ayakaKeys = r.data.items;
  }
  async function loadHistory() {
    const r = await api("/api/keys/history");
    if (!r.ok) return;
    $("#key-history").innerHTML = r.data.items.slice(0, 15).map((h) => `<li><span><span class="tag">${esc(h.action)}</span> ${esc((h.metadata && h.metadata.name) || h.target_id || "")}</span><span class="small muted">${esc(fmtDate(h.created_at))}</span></li>`).join("")
      || `<li class="muted">Belum ada aktivitas.</li>`;
  }

  function showSecret(data, title) {
    modal(`<h3>${esc(title)}</h3>
      <div class="callout danger" style="margin-bottom:14px"><strong>Salin sekarang.</strong> API Key ini hanya ditampilkan satu kali dan tidak dapat dilihat lagi.</div>
      <div class="key-secret"><code id="new-key">${esc(data.api_key)}</code><button class="btn btn-primary" type="button" id="copy-key" data-icon="copy">Copy</button></div>
      <p class="small muted" style="margin-top:12px">Simpan sebagai environment variable server, mis. <code class="inline">AYAKA_API_KEY</code>. Kirim dengan header <code class="inline">X-API-Key</code>.</p>
      <label class="check" style="margin-top:10px"><input type="checkbox" id="saved-ok"> Saya sudah menyimpan API Key ini dengan aman</label>
      <div class="row" style="justify-content:flex-end;margin-top:14px"><button class="btn btn-dark" id="close-key" disabled data-close>Selesai</button></div>`, {
      dismissable: false,
      onMount(m) {
        m.querySelector("#copy-key").addEventListener("click", () => A.copyText(data.api_key, "API Key disalin"));
        m.querySelector("#saved-ok").addEventListener("change", (e) => { m.querySelector("#close-key").disabled = !e.target.checked; });
      },
    });
  }

  async function openGenerate() {
    await perms();
    modal(`<h3>Generate API Key</h3>
      <form id="gen-form" novalidate>
        <div class="field"><label for="g-name">Nama key</label><input class="input" id="g-name" required maxlength="80" placeholder="Server Produksi"></div>
        <div class="field"><label for="g-desc">Deskripsi (opsional)</label><input class="input" id="g-desc" maxlength="300"></div>
        <div class="field"><label>Permission</label>${permGrid(["profile:read"])}</div>
        <div class="two-col" style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
          <div class="field"><label for="g-exp">Kedaluwarsa</label><select class="input" id="g-exp"><option value="">Tidak ada</option><option value="7">7 hari</option><option value="30">30 hari</option><option value="90" selected>90 hari</option><option value="365">1 tahun</option></select></div>
          <div class="field"><label for="g-rl">Rate limit / menit</label><input class="input" id="g-rl" type="number" min="1" max="1000" placeholder="Default"></div>
        </div>
        <div class="row" style="justify-content:flex-end"><button class="btn" type="button" data-close>Batal</button><button class="btn btn-primary" type="submit" data-icon="key">Generate</button></div>
      </form>`, {
      onMount(m, close) {
        m.querySelector("#gen-form").addEventListener("submit", async (e) => {
          e.preventDefault();
          const name = m.querySelector("#g-name").value.trim();
          const permissions = $$("input[name=perm]:checked", m).map((i) => i.value);
          if (!name) return toast("Nama key wajib diisi", "error");
          if (!permissions.length) return toast("Pilih minimal satu permission", "error");
          const body = { name, description: m.querySelector("#g-desc").value.trim(), permissions };
          const exp = m.querySelector("#g-exp").value, rl = m.querySelector("#g-rl").value;
          if (exp) body.expires_in_days = parseInt(exp, 10);
          if (rl) body.rate_limit_per_minute = parseInt(rl, 10);
          const btn = m.querySelector("[type=submit]");
          setLoading(btn, true);
          const r = await api("/api/keys/generate", { method: "POST", body });
          setLoading(btn, false);
          if (!r.ok) return toast(r.message, "error", 6000);
          close();
          showSecret(r.data, "API Key berhasil dibuat");
          load(); loadHistory();
        });
      },
    });
  }

  async function openDetail(id) {
    const r = await api("/api/keys/" + id);
    if (!r.ok) return toast(r.message, "error");
    const k = r.data;
    const usage = (k.usage_by_day || []).length ? `<h4>Pemakaian 14 hari</h4><div class="chart-box" style="height:160px"><canvas id="kd-chart"></canvas></div>` : "";
    modal(`<h3>${esc(k.name)}</h3><dl class="kv">
      <dt>ID</dt><dd class="mono small">${esc(k.id)}</dd><dt>Key</dt><dd><code>${esc(k.masked_key)}</code></dd><dt>Status</dt><dd>${Dash.statusBadge(k.status)}</dd>
      <dt>Permission</dt><dd>${k.permissions.map((p) => `<code>${esc(p)}</code>`).join(" ")}</dd><dt>Rate limit</dt><dd>${k.rate_limit_per_minute} / menit</dd>
      <dt>Dipakai</dt><dd>${fmtNum(k.usage_count)}× · terakhir ${esc(timeAgo(k.last_used_at))}</dd>
      <dt>Request tercatat</dt><dd>${fmtNum(k.stats.total)} (${fmtNum(k.stats.success)} berhasil · ${fmtNum(k.stats.failed)} gagal · rata-rata ${k.stats.avg_ms} ms)</dd><dt>Dibuat</dt><dd>${esc(fmtDate(k.created_at))}</dd>
      <dt>Kedaluwarsa</dt><dd>${esc(k.expires_at ? fmtDate(k.expires_at) : "Tidak ada")}</dd>
      ${k.revoked_at ? `<dt>Dicabut</dt><dd>${esc(fmtDate(k.revoked_at))} — ${esc(k.revoked_reason || "")}</dd>` : ""}</dl>${usage}
      <div class="row" style="justify-content:flex-end;margin-top:16px"><a class="btn" href="#logs" data-close>Lihat logs</a><button class="btn btn-dark" data-close>Tutup</button></div>`, {
      onMount(m) {
        if (usage && window.AyakaCharts) {
          delete AyakaCharts.charts["kd-chart"];
          const s = AyakaCharts.series(k.usage_by_day, "day", "requests");
          AyakaCharts.render("kd-chart", "bar", s.labels, [{ label: "Request", data: s.data }]);
        }
        const logsLink = m.querySelector('a[href="#logs"]');
        logsLink.addEventListener("click", () => setTimeout(() => { const sel = $("#lf-key"); if (sel) { sel.value = k.id; $("#log-filter").requestSubmit(); } }, 300));
      },
    });
  }

  async function openEdit(id) {
    await perms();
    const k = (window.__ayakaKeys || []).find((x) => x.id === id);
    if (!k) return;
    modal(`<h3>Edit API Key</h3><form id="edit-form" novalidate>
      <div class="field"><label for="e-name">Nama</label><input class="input" id="e-name" required maxlength="80" value="${esc(k.name)}"></div>
      <div class="field"><label for="e-desc">Deskripsi</label><input class="input" id="e-desc" maxlength="300" value="${esc(k.description || "")}"></div>
      <div class="field"><label>Permission</label>${permGrid(k.permissions)}</div>
      <div class="field"><label for="e-rl">Rate limit / menit</label><input class="input" id="e-rl" type="number" min="1" max="1000" value="${k.rate_limit_per_minute}"></div>
      <div class="row" style="justify-content:flex-end"><button class="btn" type="button" data-close>Batal</button><button class="btn btn-primary" type="submit">Simpan</button></div></form>`, {
      onMount(m, close) {
        m.querySelector("#edit-form").addEventListener("submit", async (e) => {
          e.preventDefault();
          const permissions = $$("input[name=perm]:checked", m).map((i) => i.value);
          if (!permissions.length) return toast("Pilih minimal satu permission", "error");
          const r = await api("/api/keys/" + id, { method: "PATCH", body: { name: m.querySelector("#e-name").value.trim(), description: m.querySelector("#e-desc").value.trim(), permissions, rate_limit_per_minute: parseInt(m.querySelector("#e-rl").value, 10) } });
          if (!r.ok) return toast(r.message, "error");
          close(); toast("API Key diperbarui", "success"); load(); loadHistory();
        });
      },
    });
  }

  async function regen(id) {
    const ok = await confirmDialog({ title: "Regenerate API Key?", body: "Key lama akan <strong>langsung dicabut</strong> dan diganti key baru dengan permission yang sama. Aplikasi yang memakai key lama akan berhenti bekerja.", confirmText: "Regenerate", danger: true });
    if (!ok) return;
    const r = await api(`/api/keys/${id}/regenerate`, { method: "POST" });
    if (!r.ok) return toast(r.message, "error");
    showSecret(r.data, "API Key baru");
    load(); loadHistory();
  }
  async function revoke(id, name) {
    const ok = await confirmDialog({ title: "Revoke API Key?", body: `Key <strong>${esc(name)}</strong> akan dicabut permanen dan seluruh request dengan key ini langsung ditolak.`, confirmText: "Revoke", danger: true, requireText: "REVOKE" });
    if (!ok) return;
    const r = await api("/api/keys/" + id, { method: "DELETE", body: { reason: "Dicabut oleh pemilik dari dashboard" } });
    if (!r.ok) return toast(r.message, "error");
    toast("API Key dicabut", "success"); load(); loadHistory();
  }

  document.addEventListener("DOMContentLoaded", () => {
    $("#key-new").addEventListener("click", openGenerate);
    $("#key-filter").addEventListener("click", (e) => {
      const b = e.target.closest("button[data-status]");
      if (!b) return;
      $$("#key-filter button").forEach((x) => x.classList.toggle("on", x === b));
      filter = b.dataset.status; load();
    });
    $("#key-rows").addEventListener("click", (e) => {
      const t = e.target.closest("button");
      if (!t) return;
      if (t.dataset.kDetail) openDetail(t.dataset.kDetail);
      if (t.dataset.kEdit) openEdit(t.dataset.kEdit);
      if (t.dataset.kRegen) regen(t.dataset.kRegen);
      if (t.dataset.kRevoke) revoke(t.dataset.kRevoke, t.dataset.name);
    });
  });
  Dash.register("keys", { load() { load(); loadHistory(); }, poll: load });
})();
