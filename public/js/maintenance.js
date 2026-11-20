/* AYAKA API — maintenance page: shows admin's message, returns users automatically when finished */
(function () {
  "use strict";
  const { api, $, fmtDate, toast } = window.Ayaka;
  async function check(manual) {
    const r = await api("/api/system/status", { handleAuth: false });
    if (!r.ok) { if (manual) toast("Server belum dapat dihubungi", "error"); return; }
    const m = r.data.maintenance;
    if (!m.active) { location.replace("/"); return; }
    if (m.message) $("#mt-message").textContent = m.message;
    $("#mt-window").textContent = m.end_at ? `Perkiraan selesai: ${fmtDate(m.end_at)}` : "";
    if (manual) toast("Masih dalam maintenance", "info");
  }
  document.addEventListener("DOMContentLoaded", () => {
    check(false);
    $("#mt-retry").addEventListener("click", () => check(true));
    setInterval(() => { if (!document.hidden) check(false); }, 30000);
  });
})();
