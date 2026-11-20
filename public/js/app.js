/* =====================================================================
   AYAKA API — Core frontend runtime (shared by every page)
   Security: session lives in an HttpOnly cookie. JS only reads the
   non-HttpOnly CSRF cookie to echo it in the X-CSRF-Token header.
   Nothing secret is ever written to localStorage.
   ===================================================================== */
(function () {
  "use strict";

  const ICONS = {
    home: '<path d="M3 11l9-8 9 8"/><path d="M5 10v10h14V10"/><path d="M10 20v-6h4v6"/>',
    key: '<circle cx="7.5" cy="15.5" r="4.5"/><path d="M10.7 12.3L21 2"/><path d="M16 7l3 3"/><path d="M18 5l2 2"/>',
    book: '<path d="M4 4h11a4 4 0 014 4v12H8a4 4 0 01-4-4z"/><path d="M4 16a4 4 0 014-4h11"/>',
    play: '<path d="M6 4l14 8-14 8z"/>',
    spark: '<path d="M12 2l2.4 6.6L21 11l-6.6 2.4L12 20l-2.4-6.6L3 11l6.6-2.4z"/>',
    chart: '<path d="M3 3v18h18"/><path d="M7 15l4-4 3 3 5-6"/>',
    list: '<path d="M8 6h13M8 12h13M8 18h13"/><circle cx="3.5" cy="6" r="1"/><circle cx="3.5" cy="12" r="1"/><circle cx="3.5" cy="18" r="1"/>',
    hook: '<path d="M18 16.98h-5.99c-1.1 0-1.95.94-2.48 1.9A4 4 0 012 17c.01-.7.2-1.4.57-2"/><path d="M6 17l3.13-5.78c.53-.97.1-2.18-.5-3.1a4 4 0 116.89-4.06"/><path d="M12 6l3.13 5.73C15.66 12.7 16.9 13 18 13a4 4 0 010 8"/>',
    user: '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0116 0"/>',
    shield: '<path d="M12 2l8 3v6c0 5-3.5 9-8 11-4.5-2-8-6-8-11V5z"/><path d="M9 12l2 2 4-4"/>',
    help: '<circle cx="12" cy="12" r="10"/><path d="M9.1 9a3 3 0 015.8 1c0 2-3 3-3 3"/><path d="M12 17h.01"/>',
    logout: '<path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4"/><path d="M16 17l5-5-5-5"/><path d="M21 12H9"/>',
    bell: '<path d="M6 8a6 6 0 0112 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.94 1.94 0 003.4 0"/>',
    menu: '<path d="M3 6h18M3 12h18M3 18h18"/>',
    collapse: '<path d="M15 18l-6-6 6-6"/><path d="M21 4v16"/>',
    copy: '<rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/>',
    trash: '<path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M19 6l-1 14H6L5 6"/>',
    refresh: '<path d="M21 12a9 9 0 11-3-6.7L21 8"/><path d="M21 3v5h-5"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
    moon: '<path d="M21 12.8A9 9 0 1111.2 3a7 7 0 009.8 9.8z"/>',
    eye: '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
    mail: '<rect x="2" y="4" width="20" height="16" rx="2"/><path d="M22 6l-10 7L2 6"/>',
    lock: '<rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0110 0v4"/>',
    bolt: '<path d="M13 2L3 14h9l-1 8 10-12h-9z"/>',
    users: '<circle cx="9" cy="7" r="4"/><path d="M2 21a7 7 0 0114 0"/><path d="M16 3.1a4 4 0 010 7.8M22 21a7 7 0 00-4-6.3"/>',
    server: '<rect x="2" y="3" width="20" height="8" rx="2"/><rect x="2" y="13" width="20" height="8" rx="2"/><path d="M6 7h.01M6 17h.01"/>',
    settings: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 00.3 1.8l.1.1a2 2 0 11-2.8 2.8l-.1-.1a1.7 1.7 0 00-1.8-.3 1.7 1.7 0 00-1 1.5V21a2 2 0 11-4 0v-.1a1.7 1.7 0 00-1.1-1.5 1.7 1.7 0 00-1.8.3l-.1.1a2 2 0 11-2.8-2.8l.1-.1a1.7 1.7 0 00.3-1.8 1.7 1.7 0 00-1.5-1H3a2 2 0 110-4h.1a1.7 1.7 0 001.5-1.1 1.7 1.7 0 00-.3-1.8l-.1-.1a2 2 0 112.8-2.8l.1.1a1.7 1.7 0 001.8.3H9a1.7 1.7 0 001-1.5V3a2 2 0 114 0v.1a1.7 1.7 0 001 1.5 1.7 1.7 0 001.8-.3l.1-.1a2 2 0 112.8 2.8l-.1.1a1.7 1.7 0 00-.3 1.8V9a1.7 1.7 0 001.5 1H21a2 2 0 110 4h-.1a1.7 1.7 0 00-1.5 1z"/>',
    megaphone: '<path d="M3 11v2a1 1 0 001 1h3l5 4V6L7 10H4a1 1 0 00-1 1z"/><path d="M16 8a5 5 0 010 8"/><path d="M19 5a9 9 0 010 14"/>',
    tool: '<path d="M14.7 6.3a1 1 0 000 1.4l1.6 1.6a1 1 0 001.4 0l3.8-3.8a6 6 0 01-7.9 7.9l-6.9 6.9a2.1 2.1 0 01-3-3l6.9-6.9a6 6 0 017.9-7.9z"/>',
    search: '<circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/>',
    download: '<path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><path d="M7 10l5 5 5-5"/><path d="M12 15V3"/>',
    sync: '<path d="M21 12a9 9 0 01-15.5 6.3L3 16"/><path d="M3 12a9 9 0 0115.5-6.3L21 8"/><path d="M21 3v5h-5M3 21v-5h5"/>',
    github: '<path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.9a3.4 3.4 0 00-.9-2.6c3.1-.4 6.4-1.5 6.4-6.9A5.4 5.4 0 0020 4.8 5 5 0 0019.9 1S18.7.6 16 2.5a13.4 13.4 0 00-7 0C6.3.6 5.1 1 5.1 1A5 5 0 005 4.8a5.4 5.4 0 00-1.5 3.7c0 5.4 3.3 6.5 6.4 6.9a3.4 3.4 0 00-.9 2.6V22"/>',
    whatsapp: '<path d="M3 21l1.7-5A9 9 0 1121 12a9 9 0 01-13 8z"/><path d="M9 9.5c0 3 2.5 5.5 5.5 5.5l1-1.5-2-1-1 .8a4 4 0 01-2-2l.8-1-1-2z"/>',
    x: '<path d="M18 6L6 18M6 6l12 12"/>',
    check: '<path d="M20 6L9 17l-5-5"/>',
    globe: '<circle cx="12" cy="12" r="10"/><path d="M2 12h20M12 2a15 15 0 010 20 15 15 0 010-20"/>',
  };

  function icon(name, cls) {
    const p = ICONS[name] || ICONS.spark;
    return `<svg class="${cls || ""}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${p}</svg>`;
  }
  function hydrateIcons(root) {
    (root || document).querySelectorAll("[data-icon]").forEach((el) => {
      if (el.dataset.iconDone) return;
      el.insertAdjacentHTML("afterbegin", icon(el.dataset.icon));
      el.dataset.iconDone = "1";
    });
  }

  const esc = (v) => String(v == null ? "" : v).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const $ = (s, r) => (r || document).querySelector(s);
  const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));
  const nf = new Intl.NumberFormat("id-ID");
  const fmtNum = (n) => nf.format(Number(n || 0));
  function fmtDate(iso, withTime = true) {
    if (!iso) return "—";
    const d = new Date(iso);
    return d.toLocaleString("id-ID", withTime ? { dateStyle: "medium", timeStyle: "short" } : { dateStyle: "medium" });
  }
  function timeAgo(iso) {
    if (!iso) return "Belum pernah";
    const s = Math.round((Date.now() - new Date(iso).getTime()) / 1000);
    if (s < 0) return "baru saja";
    if (s < 60) return s + " dtk lalu";
    if (s < 3600) return Math.floor(s / 60) + " mnt lalu";
    if (s < 86400) return Math.floor(s / 3600) + " jam lalu";
    return Math.floor(s / 86400) + " hari lalu";
  }

  function getCookie(name) {
    const m = document.cookie.split("; ").find((c) => c.startsWith(name + "="));
    return m ? decodeURIComponent(m.split("=").slice(1).join("=")) : "";
  }
  const csrf = () => getCookie("__Host-ayaka_csrf") || getCookie("ayaka_csrf");

  /** fetch wrapper → { ok, status, json, data, message, code, ms, headers } */
  async function api(path, opts = {}) {
    const method = (opts.method || "GET").toUpperCase();
    const headers = Object.assign({ Accept: "application/json" }, opts.headers || {});
    let body = opts.body;
    if (body !== undefined && !(body instanceof FormData) && typeof body !== "string") {
      headers["Content-Type"] = "application/json";
      body = JSON.stringify(body);
    }
    if (method !== "GET" && method !== "HEAD" && !headers["X-API-Key"]) headers["X-CSRF-Token"] = csrf();
    const t0 = performance.now();
    let res, json = null;
    try {
      res = await fetch(path, { method, headers, body, credentials: "same-origin", signal: opts.signal });
    } catch (e) {
      if (e.name === "AbortError") throw e;
      return { ok: false, status: 0, json: null, data: null, message: "Tidak dapat terhubung ke server", code: "NETWORK_ERROR", ms: 0 };
    }
    const ms = Math.round(performance.now() - t0);
    const text = await res.text();
    try { json = text ? JSON.parse(text) : null; } catch (e) { json = null; }
    const out = {
      ok: res.ok, status: res.status, json, raw: text, headers: res.headers, ms,
      data: json && json.data, message: (json && json.message) || res.statusText,
      code: json && json.error && json.error.code,
    };
    if (opts.handleAuth !== false && res.status === 401 && document.body.dataset.guard === "auth") {
      location.href = "/login?next=" + encodeURIComponent(location.pathname + location.hash);
    }
    if (res.status === 503 && out.code === "MAINTENANCE_MODE" && document.body.dataset.guard === "auth") {
      location.href = "/maintenance";
    }
    return out;
  }

  /* ---------- Toasts ---------- */
  function toast(message, type = "info", ms = 3800) {
    let stack = $(".toast-stack");
    if (!stack) {
      stack = document.createElement("div");
      stack.className = "toast-stack";
      stack.setAttribute("role", "status");
      stack.setAttribute("aria-live", "polite");
      document.body.appendChild(stack);
    }
    const el = document.createElement("div");
    el.className = "toast " + type;
    el.innerHTML = `${icon(type === "error" ? "x" : type === "success" ? "check" : "bell")}<div>${esc(message)}</div>`;
    el.querySelector("svg").style.cssText = "width:20px;height:20px;flex:none";
    stack.appendChild(el);
    setTimeout(() => { el.classList.add("out"); setTimeout(() => el.remove(), 260); }, ms);
  }

  /* ---------- Modal ---------- */
  function modal(html, { onMount, onClose, dismissable = true } = {}) {
    const bd = document.createElement("div");
    bd.className = "modal-backdrop";
    bd.innerHTML = `<div class="modal card" role="dialog" aria-modal="true">${html}</div>`;
    let closed = false;
    const close = () => { if (closed) return; closed = true; bd.remove(); document.removeEventListener("keydown", onKey); if (onClose) onClose(); };
    const onKey = (e) => { if (e.key === "Escape" && dismissable) close(); };
    if (dismissable) bd.addEventListener("click", (e) => { if (e.target === bd) close(); });
    document.addEventListener("keydown", onKey);
    document.body.appendChild(bd);
    hydrateIcons(bd);
    bd.querySelectorAll("[data-close]").forEach((b) => b.addEventListener("click", close));
    const first = bd.querySelector("input,select,textarea,button");
    if (first) setTimeout(() => first.focus(), 30);
    if (onMount) onMount(bd.querySelector(".modal"), close);
    return close;
  }
  function confirmDialog({ title, body, confirmText = "Konfirmasi", danger = false, requireText = null }) {
    return new Promise((resolve) => {
      let done = false;
      const close = modal(`
        <h3>${esc(title)}</h3><p class="muted">${body}</p>
        ${requireText ? `<div class="field"><label>Ketik <code class="inline">${esc(requireText)}</code> untuk konfirmasi</label><input class="input" data-req autocomplete="off"></div>` : ""}
        <div class="row" style="justify-content:flex-end;margin-top:12px">
          <button class="btn" data-close>Batal</button>
          <button class="btn ${danger ? "btn-danger" : "btn-primary"}" data-ok ${requireText ? "disabled" : ""}>${esc(confirmText)}</button>
        </div>`, {
        onMount(m, closeFn) {
          const ok = m.querySelector("[data-ok]");
          const req = m.querySelector("[data-req]");
          if (req) req.addEventListener("input", () => { ok.disabled = req.value.trim() !== requireText; });
          ok.addEventListener("click", () => { done = true; closeFn(); resolve(req ? req.value.trim() : true); });
        },
        onClose() { if (!done) resolve(false); },
      });
      void close;
    });
  }

  async function copyText(text, label = "Disalin ke clipboard") {
    try {
      await navigator.clipboard.writeText(text);
    } catch (e) {
      const ta = document.createElement("textarea");
      ta.value = text; document.body.appendChild(ta); ta.select(); document.execCommand("copy"); ta.remove();
    }
    toast(label, "success", 2000);
  }

  function setLoading(btn, on) {
    if (!btn) return;
    btn.classList.toggle("is-loading", on);
    btn.disabled = on;
  }

  /* ---------- Theme ---------- */
  function applyThemeIcon() {
    const dark = document.documentElement.getAttribute("data-theme") === "dark";
    $$("[data-theme-toggle]").forEach((b) => {
      b.innerHTML = icon(dark ? "sun" : "moon");
      b.setAttribute("aria-label", dark ? "Mode terang" : "Mode gelap");
      b.title = dark ? "Mode terang" : "Mode gelap";
    });
  }
  function toggleTheme() {
    const next = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    try { localStorage.setItem("ayaka-theme", next); } catch (e) { /* ignore */ }
    applyThemeIcon();
    document.dispatchEvent(new CustomEvent("ayaka:theme", { detail: next }));
  }

  /* ---------- Scroll reveal (re-animates in both directions, no flicker) ---------- */
  const reduceMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  let revealObserver = null;
  function initReveal(root) {
    const els = $$(".reveal", root);
    if (reduceMotion || !("IntersectionObserver" in window)) { els.forEach((e) => e.classList.add("in")); return; }
    if (!revealObserver) {
      revealObserver = new IntersectionObserver((entries) => {
        entries.forEach((en) => {
          if (en.isIntersecting && en.intersectionRatio >= 0.12) en.target.classList.add("in");
          else if (!en.isIntersecting) en.target.classList.remove("in"); // fully out of view → can replay
        });
      }, { threshold: [0, 0.12], rootMargin: "0px 0px -6% 0px" });
    }
    els.forEach((e, i) => {
      // Elemen hero (di atas lipatan) langsung tampil — jangan menunggu scroll.
      if (e.closest(".hero")) { requestAnimationFrame(() => e.classList.add("in")); return; }
      if (!e.style.getPropertyValue("--d") && e.parentElement && e.parentElement.dataset.stagger !== undefined) {
        e.style.setProperty("--d", (Array.from(e.parentElement.children).indexOf(e) * 0.07).toFixed(2) + "s");
      }
      revealObserver.observe(e);
      void i;
    });
  }

  function animateCount(el, to, duration = 1100) {
    to = Number(to || 0);
    const from = Number(el.dataset.current || 0);
    if (reduceMotion || from === to) { el.textContent = fmtNum(to); el.dataset.current = to; return; }
    const t0 = performance.now();
    const step = (t) => {
      const p = Math.min(1, (t - t0) / duration);
      const eased = 1 - Math.pow(1 - p, 3);
      el.textContent = fmtNum(Math.round(from + (to - from) * eased));
      if (p < 1) requestAnimationFrame(step); else el.dataset.current = to;
    };
    requestAnimationFrame(step);
  }
  function initCounters(root) {
    const els = $$("[data-count]", root);
    if (!("IntersectionObserver" in window)) { els.forEach((e) => animateCount(e, e.dataset.count)); return; }
    const io = new IntersectionObserver((entries) => {
      entries.forEach((en) => {
        if (en.isIntersecting) { en.target.dataset.current = 0; animateCount(en.target, en.target.dataset.count); }
      });
    }, { threshold: 0.4 });
    els.forEach((e) => io.observe(e));
  }

  /* ---------- Code tabs & copy ---------- */
  function initTabs(root) {
    $$("[data-tabs]", root).forEach((wrap) => {
      const tabs = $$(".tab[data-tab]", wrap);
      const panes = $$("[data-pane]", wrap);
      const show = (name) => {
        tabs.forEach((t) => t.setAttribute("aria-selected", t.dataset.tab === name ? "true" : "false"));
        panes.forEach((p) => p.classList.toggle("hidden", p.dataset.pane !== name));
      };
      wrap._show = (name) => { if (tabs.some((t) => t.dataset.tab === name)) show(name); };
      tabs.forEach((t) => t.addEventListener("click", () => {
        show(t.dataset.tab);
        if (wrap.dataset.tabs === "lang") {
          try { sessionStorage.setItem("ayaka-lang", t.dataset.tab); } catch (e) { /* ignore */ }
          $$('[data-tabs="lang"]').forEach((other) => { if (other !== wrap && other._show) other._show(t.dataset.tab); });
        }
      }));
      let pref = null;
      try { pref = wrap.dataset.tabs === "lang" ? sessionStorage.getItem("ayaka-lang") : null; } catch (e) { /* ignore */ }
      show(pref && tabs.some((t) => t.dataset.tab === pref) ? pref : (tabs[0] && tabs[0].dataset.tab));
      const copy = $(".tab-copy", wrap);
      if (copy) copy.addEventListener("click", () => {
        const visible = panes.find((p) => !p.classList.contains("hidden"));
        if (visible) copyText(visible.innerText, "Kode disalin");
      });
    });
    $$("[data-copy]", root).forEach((b) => b.addEventListener("click", () => {
      const t = b.dataset.copy.startsWith("#") ? ($(b.dataset.copy) || {}).innerText : b.dataset.copy;
      copyText(t || "");
    }));
  }

  /* ---------- Nav ---------- */
  function initNav() {
    const burger = $(".nav-burger");
    const links = $(".nav-links");
    if (burger && links) {
      burger.addEventListener("click", () => {
        const open = links.classList.toggle("open");
        burger.setAttribute("aria-expanded", open ? "true" : "false");
      });
      links.addEventListener("click", (e) => { if (e.target.closest("a")) links.classList.remove("open"); });
    }
    $$("[data-theme-toggle]").forEach((b) => b.addEventListener("click", toggleTheme));
    applyThemeIcon();
    // Auth-aware nav: swap Login/Register for Dashboard when a session exists.
    const authSlot = $("[data-auth-slot]");
    if (authSlot) {
      api("/api/auth/me", { handleAuth: false }).then((r) => {
        if (r.ok) {
          authSlot.innerHTML = `<a class="btn btn-primary btn-sm" href="${r.data.is_admin ? "/admin" : "/dashboard"}">${icon("home")}Dashboard</a>`;
        }
      });
    }
  }

  /* ---------- Smooth page transition ---------- */
  function initPageTransitions() {
    document.body.classList.add("page-enter");
    if (reduceMotion) return;
    document.addEventListener("click", (e) => {
      const a = e.target.closest("a[href]");
      if (!a || a.target === "_blank" || e.metaKey || e.ctrlKey || e.shiftKey || a.hasAttribute("download")) return;
      const url = new URL(a.href, location.href);
      if (url.origin !== location.origin || (url.pathname === location.pathname && url.hash) || url.pathname.startsWith("/api/")) return;
      if (a.dataset.noTransition !== undefined) return;
      e.preventDefault();
      document.body.classList.add("page-leave");
      setTimeout(() => { location.href = url.href; }, 160);
    });
    window.addEventListener("pageshow", () => document.body.classList.remove("page-leave"));
  }

  /* ---------- Privacy-friendly visitor tracking ---------- */
  function track() {
    if (navigator.doNotTrack === "1" || navigator.globalPrivacyControl) return;
    const send = () => api("/api/track", { method: "POST", body: { path: location.pathname, referrer: document.referrer || null }, handleAuth: false });
    if ("requestIdleCallback" in window) requestIdleCallback(send); else setTimeout(send, 600);
  }

  /* ---------- Maintenance + announcements ---------- */
  async function systemStatus() {
    const page = document.body.dataset.page || "";
    const r = await api("/api/system/status", { handleAuth: false });
    if (!r.ok || !r.data) return null;
    const m = r.data.maintenance;
    if (m.active && ["landing", "docs", "register", "forgot", "reset"].includes(page)) {
      const me = await api("/api/auth/me", { handleAuth: false });
      if (!(me.ok && me.data.is_admin)) { location.href = "/maintenance"; return r.data; }
    }
    const slot = $("[data-announcements]");
    if (slot) {
      const items = (r.data.announcements || []).slice(0, 2).map((a) =>
        `<div class="announce ${esc(a.level)}"><strong>${esc(a.title)}</strong> — ${esc(a.body)}</div>`);
      if (m.scheduled) items.unshift(`<div class="announce warning"><strong>Maintenance terjadwal</strong> — mulai ${esc(fmtDate(m.start_at))}. ${esc(m.message || "")}</div>`);
      slot.innerHTML = items.join("");
    }
    return r.data;
  }

  function serializeForm(form) {
    const out = {};
    new FormData(form).forEach((v, k) => { out[k] = typeof v === "string" ? v.trim() : v; });
    return out;
  }

  window.Ayaka = {
    api, toast, modal, confirmDialog, copyText, setLoading, icon, hydrateIcons, esc, $, $$, fmtNum, fmtDate,
    timeAgo, initReveal, initCounters, animateCount, initTabs, serializeForm, systemStatus, csrf, toggleTheme,
    BASE_URL: location.origin,
  };

  document.addEventListener("DOMContentLoaded", () => {
    hydrateIcons();
    initNav();
    initReveal();
    initCounters();
    initTabs();
    initPageTransitions();
    $$("[data-year]").forEach((e) => { e.textContent = new Date().getFullYear(); });
    $$("[data-base-url]").forEach((e) => { e.textContent = location.origin; });
    if (document.body.dataset.track !== "off") track();
    if (document.body.dataset.page !== "maintenance") systemStatus();
  });
})();
