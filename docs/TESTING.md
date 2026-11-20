# Panduan Pengujian AYAKA API

## 1. Test otomatis (pytest)

Test memakai **PostgreSQL sungguhan**, bukan database sementara di memori. Gunakan Postgres lokal atau **branch Neon khusus test**.
**Perhatian:** skema di database test akan di-drop dan dibuat ulang setiap kali test dijalankan, jadi jangan pernah mengarahkannya ke database production.

```bash
pip install -r requirements-dev.txt
createdb ayaka_test                       # atau buat branch "test" di Neon
export TEST_DATABASE_URL=postgresql://postgres:postgres@localhost/ayaka_test
pytest -q
```

Hasil yang diharapkan: `35 passed`. Pemanggilan Resend di-*mock* di dalam test, sehingga tidak ada email sungguhan yang terkirim.

| File | Cakupan |
|---|---|
| `tests/test_auth.py` | health, register (sukses, email duplikat, validasi), login/logout + cookie sesi, sesi kedaluwarsa, brute-force lockout, CSRF wajib untuk aksi tulis via sesi, lupa/reset password, `/dashboard` wajib login |
| `tests/test_api_keys.py` | format `ayaka_live_` + tersimpan sebagai hash, key valid/tidak valid, key di URL ditolak, key revoked/expired ditolak, permission, isolasi antar-user, manajemen key wajib sesi, regenerate, rate limit per key, log tidak menyimpan secret, revoke via API Key (`keys:revoke`) |
| `tests/test_magic_link.py` | siklus penuh Premium (send → verif sekali pakai → status → renew → revoke), token kedaluwarsa, token tidak valid, isolasi tenant, kegagalan email dilaporkan, permission premium |
| `tests/test_analytics_admin.py` | analytics sesuai isi database, visitor unik, filter logs + export CSV, kontrol akses admin, maintenance mode (503), format error konsisten, batas ukuran request |

## 2. Checklist uji manual (setelah deploy)

| # | Langkah | Hasil yang diharapkan |
|---|---|---|
| 1 | Buka `/` | Landing tampil, terminal hero memuat `/api/health` sungguhan, statistik publik dari DB |
| 2 | Register akun baru | Diarahkan ke `/dashboard`; password lemah ditolak |
| 3 | Logout lalu login dengan password salah 5× | Akun terkunci sementara (`ACCOUNT_LOCKED`) |
| 4 | Lupa password | Email reset masuk; link berfungsi sekali, lalu sesi lama dicabut |
| 5 | Generate API Key | Key `ayaka_live_…` tampil satu kali; tombol Selesai aktif setelah checkbox dicentang |
| 6 | Playground → `GET /api/user/profile` | `200` berisi data akun; key tidak disimpan di browser |
| 7 | Request Logs | Request tadi muncul; filter dan Export CSV berfungsi |
| 8 | Analytics | Grafik bertambah tanpa reload (polling 4 detik) |
| 9 | Magic Link Premium → kirim ke email Anda | Email masuk; klik tombol menghasilkan *Premium aktif*; link kedua kali ditolak |
| 10 | Cek status / renew / revoke | Status berubah dan email notifikasi terkirim |
| 11 | Webhook → isi URL (mis. https://webhook.site), kirim test | Request masuk dengan header `X-Ayaka-Signature` |
| 12 | Revoke API Key | Request berikutnya dengan key itu → `401 API_KEY_REVOKED` |
| 13 | `/admin` sebagai non-admin | Diarahkan ke dashboard |
| 14 | Admin → maintenance ON | API publik `503`, halaman publik menuju `/maintenance`; admin tetap bisa masuk |
| 15 | Admin → pengumuman | Banner muncul di landing dan dashboard |
| 16 | Mode gelap & tampilan ponsel | Dock bawah muncul, tidak ada scroll horizontal |

## 3. Contoh cURL

```bash
BASE=https://DOMAIN-ANDA            # atau http://localhost:8000
KEY=ayaka_live_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

curl $BASE/api/health
curl -H "X-API-Key: $KEY" $BASE/api/user/profile
curl -H "X-API-Key: $KEY" "$BASE/api/keys?status=active"
curl -H "X-API-Key: $KEY" "$BASE/api/logs?per_page=5"
curl -H "X-API-Key: $KEY" $BASE/api/analytics

# Magic Link Premium
curl -X POST $BASE/api/am/send   -H "X-API-Key: $KEY" -H "Content-Type: application/json" -d '{"email":"user@example.com","plan":"premium"}'
curl "$BASE/api/am/status?email=user@example.com" -H "X-API-Key: $KEY"
curl -X POST $BASE/api/am/renew  -H "X-API-Key: $KEY" -H "Content-Type: application/json" -d '{"email":"user@example.com","duration_days":30}'
curl -X POST $BASE/api/am/revoke -H "X-API-Key: $KEY" -H "Content-Type: application/json" -d '{"email":"user@example.com","reason":"Refund"}'
curl -X POST $BASE/api/am/verif  -H "Content-Type: application/json" -d '{"token":"TOKEN_DARI_EMAIL"}'

# Revoke key (permission keys:revoke)
curl -X DELETE $BASE/api/keys/KEY_ID -H "X-API-Key: $KEY"

# Uji error
curl -H "X-API-Key: ayaka_live_salah" $BASE/api/user/profile        # 401 INVALID_API_KEY
curl "$BASE/api/user/profile?api_key=$KEY"                          # 400 API_KEY_IN_URL
```

## 4. Contoh klien

```bash
cd examples/javascript && AYAKA_BASE_URL=$BASE AYAKA_API_KEY=$KEY node ayaka-client.js user@example.com
cd examples/python     && pip install requests && AYAKA_BASE_URL=$BASE AYAKA_API_KEY=$KEY python ayaka_client.py user@example.com
cd examples/php        && AYAKA_BASE_URL=$BASE AYAKA_API_KEY=$KEY php ayaka-client.php user@example.com
```

## 5. Verifikasi signature webhook (Node.js)

```js
import crypto from "node:crypto";
function verify(req, rawBody, secret) {
  const ts = req.headers["x-ayaka-timestamp"];
  const expected = "sha256=" + crypto.createHmac("sha256", secret).update(ts + "." + rawBody).digest("hex");
  const got = req.headers["x-ayaka-signature"] || "";
  return got.length === expected.length && crypto.timingSafeEqual(Buffer.from(got), Buffer.from(expected))
    && Math.abs(Date.now() / 1000 - Number(ts)) < 300;
}
```
