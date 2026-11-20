/* AYAKA API — Login / Register / Forgot / Reset password */
(function () {
  "use strict";
  const { api, $, $$, setLoading, toast, serializeForm, icon } = window.Ayaka;
  const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

  function safeNext() {
    const n = new URLSearchParams(location.search).get("next");
    return n && n.startsWith("/") && !n.startsWith("//") && !n.startsWith("/api/") ? n : null;
  }
  function alertBox(msg, type = "error") {
    const el = $("[data-alert]");
    if (!el) return;
    el.className = "form-alert " + type;
    el.textContent = msg;
    el.classList.toggle("hidden", !msg);
  }
  function fieldErr(name, msg) {
    const e = $(`[data-err="${name}"]`);
    const input = $(`[name="${name}"]`);
    if (e) e.textContent = msg || "";
    if (input) { input.classList.toggle("is-invalid", !!msg); input.setAttribute("aria-invalid", msg ? "true" : "false"); }
  }
  function clearErrs(form) { $$("[data-err]", form).forEach((e) => fieldErr(e.dataset.err, "")); alertBox(""); }

  function pwProblems(p) {
    const out = [];
    if (p.length < 8) out.push("minimal 8 karakter");
    if (!/[a-z]/.test(p)) out.push("huruf kecil");
    if (!/[A-Z]/.test(p)) out.push("huruf besar");
    if (!/\d/.test(p)) out.push("angka");
    return out;
  }
  function initPasswordUi() {
    $$("[data-pw-toggle]").forEach((b) => b.addEventListener("click", () => {
      const input = b.parentElement.querySelector("input");
      const show = input.type === "password";
      input.type = show ? "text" : "password";
      b.setAttribute("aria-label", show ? "Sembunyikan password" : "Tampilkan password");
      b.innerHTML = icon(show ? "x" : "eye");
    }));
    const meter = $("[data-pw-meter]");
    const pw = $('input[name="password"]');
    if (meter && pw) pw.addEventListener("input", () => {
      const score = 4 - pwProblems(pw.value).length + (pw.value.length >= 12 ? 1 : 0);
      const pct = Math.max(0, Math.min(100, score * 20));
      meter.style.width = pct + "%";
      meter.style.background = pct < 50 ? "var(--red)" : pct < 90 ? "var(--yellow)" : "var(--green)";
    });
  }

  function applyServerError(r) {
    const details = r.json && r.json.error && r.json.error.details;
    const map = { EMAIL_EXISTS: "email", INVALID_EMAIL: "email", USERNAME_EXISTS: "username", INVALID_USERNAME: "username",
      WEAK_PASSWORD: "password", PASSWORD_MISMATCH: "confirm_password" };
    if (map[r.code]) fieldErr(map[r.code], r.message);
    if (Array.isArray(details)) details.forEach((d) => d.field && fieldErr(d.field, d.message));
    alertBox(r.message || "Terjadi kesalahan");
    toast(r.message || "Terjadi kesalahan", "error");
  }

  async function redirectIfLoggedIn() {
    const r = await api("/api/auth/me", { handleAuth: false });
    if (r.ok) location.replace(safeNext() || (r.data.is_admin ? "/admin" : "/dashboard"));
  }

  function initLogin() {
    const form = $("#login-form");
    if (!form) return;
    redirectIfLoggedIn();
    const params = new URLSearchParams(location.search);
    if (params.get("registered")) alertBox("Registrasi berhasil. Silakan login.", "success");
    if (params.get("reset")) alertBox("Password berhasil direset. Silakan login.", "success");
    if (params.get("expired")) alertBox("Sesi Anda telah berakhir. Silakan login kembali.", "error");
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      clearErrs(form);
      const d = serializeForm(form);
      let bad = false;
      if (!EMAIL_RE.test(d.email || "")) { fieldErr("email", "Email tidak valid"); bad = true; }
      if (!d.password) { fieldErr("password", "Password wajib diisi"); bad = true; }
      if (bad) return;
      const btn = form.querySelector("[type=submit]");
      setLoading(btn, true);
      const r = await api("/api/auth/login", { method: "POST", body: { email: d.email, password: $("#password").value, remember_me: !!d.remember_me }, handleAuth: false });
      setLoading(btn, false);
      if (!r.ok) {
        if (r.code === "INVALID_CREDENTIALS") fieldErr("password", " ");
        return applyServerError(r);
      }
      toast("Login berhasil. Mengalihkan…", "success");
      location.href = safeNext() || r.data.redirect || "/dashboard";
    });
  }

  function initRegister() {
    const form = $("#register-form");
    if (!form) return;
    redirectIfLoggedIn();
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      clearErrs(form);
      const d = serializeForm(form);
      d.password = $("#password").value; d.confirm_password = $("#confirm_password").value;
      let bad = false;
      if (!/^[A-Za-z0-9_]{3,32}$/.test(d.username || "")) { fieldErr("username", "3–32 karakter: huruf, angka, underscore"); bad = true; }
      if ((d.full_name || "").length < 2) { fieldErr("full_name", "Nama lengkap wajib diisi"); bad = true; }
      if (!EMAIL_RE.test(d.email || "")) { fieldErr("email", "Format email tidak valid"); bad = true; }
      const pp = pwProblems(d.password);
      if (pp.length) { fieldErr("password", "Password perlu: " + pp.join(", ")); bad = true; }
      if (d.password !== d.confirm_password) { fieldErr("confirm_password", "Konfirmasi password tidak sama"); bad = true; }
      if (bad) return;
      const btn = form.querySelector("[type=submit]");
      setLoading(btn, true);
      const r = await api("/api/auth/register", { method: "POST", body: d, handleAuth: false });
      setLoading(btn, false);
      if (!r.ok) return applyServerError(r);
      toast("Registrasi berhasil! Selamat datang di AYAKA API.", "success");
      location.href = "/dashboard#keys";
    });
  }

  function initForgot() {
    const form = $("#forgot-form");
    if (!form) return;
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      clearErrs(form);
      const email = $("#email").value.trim();
      if (!EMAIL_RE.test(email)) return fieldErr("email", "Email tidak valid");
      const btn = form.querySelector("[type=submit]");
      setLoading(btn, true);
      const r = await api("/api/auth/forgot-password", { method: "POST", body: { email }, handleAuth: false });
      setLoading(btn, false);
      if (!r.ok) return applyServerError(r);
      alertBox(r.message, "success");
      form.reset();
    });
  }

  function initReset() {
    const form = $("#reset-form");
    if (!form) return;
    const token = new URLSearchParams(location.search).get("token") || "";
    if (token.length < 20) { alertBox("Tautan reset tidak valid. Minta tautan baru dari halaman Forgot Password."); form.querySelector("[type=submit]").disabled = true; }
    // Remove the token from the address bar / history after reading it.
    history.replaceState(null, "", "/reset-password");
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      clearErrs(form);
      const password = $("#password").value, confirm_password = $("#confirm_password").value;
      const pp = pwProblems(password);
      if (pp.length) return fieldErr("password", "Password perlu: " + pp.join(", "));
      if (password !== confirm_password) return fieldErr("confirm_password", "Konfirmasi password tidak sama");
      const btn = form.querySelector("[type=submit]");
      setLoading(btn, true);
      const r = await api("/api/auth/reset-password", { method: "POST", body: { token, password, confirm_password }, handleAuth: false });
      setLoading(btn, false);
      if (!r.ok) return applyServerError(r);
      location.href = "/login?reset=1";
    });
  }

  document.addEventListener("DOMContentLoaded", () => { initPasswordUi(); initLogin(); initRegister(); initForgot(); initReset(); });
})();
