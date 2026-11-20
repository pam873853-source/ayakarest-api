// AYAKA API — contoh integrasi JavaScript (Node.js 18+ / server-side). Powered by AYAKA Sync.
// Jalankan: AYAKA_BASE_URL=https://domain-anda.vercel.app AYAKA_API_KEY=ayaka_live_xxx node ayaka-client.js
// JANGAN taruh API Key di JavaScript browser — simpan di server / environment variable.

const BASE_URL = (process.env.AYAKA_BASE_URL || "http://localhost:8000").replace(/\/$/, "");
const API_KEY = process.env.AYAKA_API_KEY;
if (!API_KEY) { console.error("Set AYAKA_API_KEY terlebih dahulu"); process.exit(1); }

async function ayaka(method, path, body) {
  const res = await fetch(BASE_URL + path, {
    method,
    headers: { "X-API-Key": API_KEY, "Content-Type": "application/json", Accept: "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  const json = await res.json().catch(() => ({ success: false, message: "Respons bukan JSON" }));
  if (!res.ok || !json.success) {
    const err = new Error(json.message || `HTTP ${res.status}`);
    err.status = res.status; err.code = json.error?.code; err.details = json.error?.details;
    throw err;
  }
  return json.data;
}

export const getProfile = () => ayaka("GET", "/api/user/profile");
export const listKeys = () => ayaka("GET", "/api/keys");
export const revokeKey = (id) => ayaka("DELETE", `/api/keys/${encodeURIComponent(id)}`);
export const sendMagicLink = (email, plan = "premium", name) => ayaka("POST", "/api/am/send", { email, plan, name });
export const premiumStatus = (email) => ayaka("GET", `/api/am/status?email=${encodeURIComponent(email)}`);
export const renewPremium = (email, duration_days) => ayaka("POST", "/api/am/renew", { email, duration_days });
export const revokePremium = (email, reason) => ayaka("POST", "/api/am/revoke", { email, reason });

// Verifikasi token Magic Link (biasanya dilakukan halaman /api/am/verif secara otomatis; tidak butuh API Key).
export async function verifyToken(token) {
  const res = await fetch(BASE_URL + "/api/am/verif", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ token }),
  });
  return res.json();
}

if (import.meta.url === `file://${process.argv[1]}`) {
  try {
    console.log("Profil:", await getProfile());
    const email = process.argv[2];
    if (email) console.log("Status premium:", await premiumStatus(email));
  } catch (e) {
    console.error(`[${e.status} ${e.code}] ${e.message}`, e.details || "");
    process.exit(1);
  }
}
