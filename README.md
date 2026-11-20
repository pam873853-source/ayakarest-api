# AYAKA API

**Your API. Your Control. Your Ecosystem.**
Platform REST API Management — Powered by **AYAKA Sync** · Admin: **Ayaka Sync** · Owner: **OLPI STORE**

- Email admin: olpieditz336@gmail.com
- GitHub: https://github.com/olpigiantara-design
- Saluran WhatsApp: https://whatsapp.com/channel/0029VbEbK4dHgZWWJmXFP52o

AYAKA API adalah aplikasi full-stack (Python FastAPI + HTML/CSS/JS ES6 murni) dengan database Neon PostgreSQL dan email Resend. Aplikasi ini siap di-deploy ke Vercel. Seluruh angka, grafik, log, dan status diambil dari database. Tidak ada data dummy di jalur produksi.

---

## Fitur utama

| Area | Isi |
|---|---|
| Autentikasi | Register, login, logout, lupa/reset password lewat email (Resend). Password di-hash dengan **Argon2id**. Sesi memakai cookie **HttpOnly + Secure + SameSite=Lax** (`__Host-` prefix di production), dilindungi **CSRF double-submit token**. Ada rate limiting login/register/reset berbasis database, penguncian akun setelah login gagal berulang, serta daftar dan pencabutan sesi aktif. |
| API Key | Format `ayaka_live_<43 karakter acak>`. Key **ditampilkan satu kali**, lalu yang disimpan hanya HMAC-SHA256 (dengan `API_KEY_PEPPER`). Tersedia permission granular, kedaluwarsa, rate limit per key, regenerate, revoke, edit, riwayat aktivitas, dan statistik pemakaian 14 hari. |
| Magic Link Premium | `POST /api/am/send`, `GET/POST /api/am/verif`, `GET /api/am/status`, `POST /api/am/renew`, `POST /api/am/revoke`. Token acak 256-bit yang disimpan sebagai hash, sekali pakai, dan berlaku 15 menit. Verifikasi bersifat atomik (transaksi + `FOR UPDATE`). Paket: `premium` (30 hari), `premium_quarterly` (90), `premium_yearly` (365). |
| Email (Resend) | 6 template HTML bergaya Neo Brutalism: verifikasi Magic Link, Premium aktif, Premium diperpanjang, Premium dicabut, reset password, dan notifikasi keamanan (password diubah atau di-reset). Setiap pengiriman tercatat di `email_logs`. |
| Dashboard | Overview, API Key Manager, API Documentation, Playground, Magic Link Premium, Analytics, Request Logs, Webhook Settings, Account Settings, Security, dan Help Center, ditambah Logout. Sidebar bisa diciutkan. Di ponsel tersedia *floating dock* (Home, API Keys, Docs, Analytics, Profile). |
| Analytics | Grafik Chart.js dengan polling tiap 4 detik yang berhenti saat tab tidak aktif: request per menit/jam/hari, sukses vs gagal, key dibuat, visitor unik, dan aktivasi Premium. Ada juga daftar endpoint teratas dan distribusi status code. |
| Request Logs | Filter berdasarkan teks, endpoint, status, key, dan tanggal. Tersedia paginasi, detail per request, dan **export CSV**. API Key, token, dan password tidak pernah dicatat. |
| Webhook | Event `premium.activated`, `premium.renewed`, `premium.revoked`, `key.created`, `key.revoked`, `key.regenerated`. Payload ditandatangani dengan header `X-Ayaka-Signature: sha256=HMAC(secret, timestamp + "." + body)`. Riwayat pengiriman ikut tercatat. |
| Admin | Overview platform, manajemen pengguna (suspend/activate/hapus/kuota), semua API Key (revoke), request log global, audit log, monitoring (DB latency, email, error rate), maintenance mode terjadwal, pengumuman, registrasi on/off, default rate limit/kuota, serta polling realtime 5 detik. |
| Halaman publik | Landing page, Login, Register, Lupa/Reset Password, Dokumentasi (contoh JavaScript, PHP, Python, cURL), Status, Maintenance, dan 404. |
| Keamanan | CSP ketat (tanpa inline script), HSTS, X-Frame-Options DENY, nosniff, Referrer-Policy, Permissions-Policy, dan batas body 1 MB. Respons error memakai format standar tanpa membocorkan stack trace. API Key yang dikirim lewat URL query ditolak (`400 API_KEY_IN_URL`). |

Format respons standar:

```json
{ "success": true, "message": "Request successful", "data": { }, "timestamp": "2026-01-01T00:00:00Z" }
{ "success": false, "message": "API Key tidak valid", "error": { "code": "INVALID_API_KEY", "details": null }, "timestamp": "..." }
```

---

## Struktur folder

```
ayaka-api/
├── api/index.py                 # Entry point Vercel (ASGI FastAPI)
├── ayaka/
│   ├── config.py                # Konfigurasi dari environment variables + daftar permission
│   ├── db.py                    # Pool koneksi psycopg 3 (Neon, sslmode=require)
│   ├── security.py              # Argon2id, HMAC API Key, token, CSRF
│   ├── deps.py                  # Dependency autentikasi (session / X-API-Key / admin / permission)
│   ├── middleware.py            # Request ID, header keamanan, maintenance, logging request
│   ├── responses.py, utils.py, main.py
│   ├── routers/                 # auth, user, keys, analytics, logs, magic_link, webhooks, system, admin, pages
│   └── services/                # ratelimit, settings_store, activity, analytics, resend_client, email_templates, webhooks
├── database/
│   ├── migrations/001_init.sql  # Migrasi awal (18 tabel, index, constraint)
│   └── schema.sql               # Skema lengkap (sama dengan migrasi)
├── public/                      # File statis (disajikan CDN Vercel)
│   ├── index.html, login.html, register.html, forgot-password.html, reset-password.html
│   ├── documentation.html, status.html, maintenance.html, 404.html
│   ├── css/ (style.css, auth.css, dashboard.css, responsive.css)
│   ├── js/  (app.js, theme.js, landing.js, auth.js, dashboard.js, api-keys.js, analytics.js,
│   │         charts.js, playground.js, docs.js, admin.js, status.js, maintenance.js)
│   └── assets/favicon.svg
├── templates/                   # dashboard.html & admin.html (disajikan setelah cek sesi di server)
├── scripts/                     # migrate.py, create_admin.py, generate_secrets.py
├── examples/                    # Klien siap pakai: javascript/, php/, python/
├── tests/                       # pytest (35 test, memakai PostgreSQL sungguhan)
├── docs/DEPLOYMENT.md           # Panduan deploy 21 langkah
├── docs/TESTING.md              # Panduan pengujian
├── requirements.txt, requirements-dev.txt, vercel.json, .python-version
├── .env.example, .gitignore
└── README.md
```

---

## Environment variables

| Variabel | Wajib | Keterangan |
|---|---|---|
| `DATABASE_URL` | ya | Connection string Neon (pakai host **-pooler**, `sslmode=require`) |
| `BASE_URL` | ya | URL publik, mis. `https://ayaka-api.vercel.app`. Dipakai di link Magic Link/reset |
| `RESEND_API_KEY` | ya | API key Resend (`re_...`) |
| `EMAIL_FROM` | ya | Pengirim dari domain yang sudah diverifikasi di Resend, mis. `AYAKA API <noreply@domainanda.com>` |
| `ADMIN_EMAIL` | ya | `olpieditz336@gmail.com`. Informasi kontak owner; hak admin tetap diberikan lewat tabel `admin_users` |
| `SECRET_KEY` | ya | Minimal 32 karakter acak (hash token, visitor hash) |
| `API_KEY_PEPPER` | ya | Minimal 32 karakter acak. **Jangan diganti setelah ada key**, karena semua key lama akan menjadi tidak valid |
| `SESSION_SECRET` | ya | Minimal 32 karakter acak (hash token sesi) |
| `ENVIRONMENT` | ya | `production` (cookie Secure + `__Host-`) atau `development` (untuk http://localhost) |
| `CORS_ORIGINS` | opsional | Daftar origin yang dipisah koma untuk akses API Key dari browser lain |

Buat secret dengan perintah `python scripts/generate_secrets.py`. Semua secret hanya ada di server; frontend tidak pernah menerima secret, password, atau API Key admin.

---

## Menjalankan secara lokal

```bash
# 1. Python 3.12 + PostgreSQL lokal (atau langsung pakai branch Neon)
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt

# 2. Konfigurasi
cp .env.example .env            # isi nilainya; untuk lokal set ENVIRONMENT=development dan BASE_URL=http://localhost:8000
export $(grep -v '^#' .env | xargs)

# 3. Migrasi database (idempoten, aman dijalankan berulang)
python scripts/migrate.py

# 4. Jalankan server
uvicorn api.index:app --reload --port 8000
# buka http://localhost:8000
```

Tanpa `RESEND_API_KEY` dan `EMAIL_FROM` yang valid, endpoint pengirim email akan mengembalikan `502 EMAIL_DELIVERY_FAILED` dengan pesan yang jelas. Kegagalan itu tetap tercatat di `email_logs` dan monitoring; sistem tidak pura-pura sukses.

## Membuat akun admin (Ayaka Sync)

1. Daftar lewat `/register` memakai email `olpieditz336@gmail.com`.
2. Jalankan perintah berikut dengan `DATABASE_URL` production:
   ```bash
   python scripts/create_admin.py olpieditz336@gmail.com          # superadmin, tampil sebagai "Ayaka Sync"
   python scripts/create_admin.py email@lain.com --role admin       # admin biasa
   python scripts/create_admin.py email@lain.com --remove           # cabut hak admin
   ```
   Sebagai alternatif, jalankan SQL di Neon SQL Editor:
   ```sql
   INSERT INTO admin_users (user_id, role, display_name, created_by)
   SELECT id, 'superadmin', 'Ayaka Sync', 'sql' FROM users WHERE lower(email) = 'olpieditz336@gmail.com'
   ON CONFLICT (user_id) DO UPDATE SET role = 'superadmin';
   ```
3. Login ulang, lalu buka `/admin`.

## Contoh integrasi

Lihat folder `examples/` dan halaman `/documentation`. Contoh singkat:

```bash
curl -H "X-API-Key: ayaka_live_xxx" https://domain-anda/api/user/profile
curl -X POST -H "X-API-Key: ayaka_live_xxx" -H "Content-Type: application/json" \
     -d '{"email":"pembeli@example.com","plan":"premium"}' https://domain-anda/api/am/send
```

Spesifikasi OpenAPI interaktif tersedia di `/api/swagger`.

## Dokumen lain

- [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md): deploy ke Neon + Resend + Vercel dalam 21 langkah
- [docs/TESTING.md](docs/TESTING.md): pytest, checklist uji manual, dan contoh cURL

## Catatan arsitektur Vercel

- Seluruh backend berjalan sebagai **satu Python Serverless Function** (`api/index.py`). File statis di `public/` disajikan langsung oleh CDN Vercel.
- Vercel bersifat stateless, jadi **rate limiting, sesi, maintenance, dan statistik disimpan di PostgreSQL**, bukan di memori.
- Pengiriman webhook dan email bersifat sinkron dengan timeout pendek (agar tidak hilang saat function dibekukan), dan hasilnya selalu tercatat.
- `/dashboard` dan `/admin` dirender server setelah sesi divalidasi. Tanpa sesi, pengguna diarahkan ke `/login`.

© OLPI STORE · AYAKA API · Powered by AYAKA Sync
