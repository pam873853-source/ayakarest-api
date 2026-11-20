# Panduan Deploy AYAKA API — 21 Langkah

Stack: **Neon PostgreSQL**, **Resend**, **Vercel**, Python FastAPI. Powered by AYAKA Sync · Owner: OLPI STORE.

Kebutuhan: akun GitHub, Neon, Resend, dan Vercel, sebuah domain (untuk mengirim email lewat Resend ke alamat mana pun), serta Python 3.12 di komputer Anda.

---

### Bagian A — Database (Neon)

**1. Buat project Neon.** Masuk ke https://console.neon.tech, klik **New Project**, beri nama `ayaka-api`, lalu pilih region terdekat dengan region Vercel Anda (mis. `AWS Asia Pacific (Singapore)`).

**2. Salin connection string pooled.** Buka Dashboard, klik **Connect**, aktifkan **Connection pooling**, lalu salin URL yang host-nya mengandung `-pooler`, contoh:
`postgresql://neondb_owner:xxxx@ep-xxx-pooler.ap-southeast-1.aws.neon.tech/neondb?sslmode=require`.
URL inilah yang menjadi `DATABASE_URL`.

**3. Jalankan migrasi.** Di komputer Anda:
```bash
git clone https://github.com/olpigiantara-design/ayaka-api.git && cd ayaka-api
python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
DATABASE_URL="postgresql://...-pooler.../neondb?sslmode=require" python scripts/migrate.py
```
Output yang diharapkan: `Selesai. 18 tabel tersedia.`
Alternatif tanpa Python: buka **Neon → SQL Editor**, tempel isi `database/schema.sql`, lalu klik **Run**.

**4. Verifikasi tabel.** Di Neon SQL Editor jalankan `SELECT count(*) FROM information_schema.tables WHERE table_schema='public';`. Hasilnya harus ≥ 18.

### Bagian B — Email (Resend)

**5. Buat akun Resend** di https://resend.com.

**6. Tambahkan domain.** Buka **Domains → Add Domain**, lalu masukkan domain Anda (disarankan subdomain, mis. `mail.olpistore.com`).

**7. Pasang DNS.** Tambahkan record yang ditampilkan Resend (MX + TXT SPF + TXT DKIM `resend._domainkey`; DMARC dianjurkan) di pengelola DNS domain. Tunggu hingga status domain menjadi **Verified**.
> Tanpa domain terverifikasi, Resend hanya mengizinkan pengiriman dari `onboarding@resend.dev` ke email pemilik akun Resend. Itu cukup untuk uji coba, tapi tidak untuk pelanggan.

**8. Buat API key.** Buka **API Keys → Create API Key**, pilih permission **Sending access**, lalu salin nilai `re_...`. Nilai ini menjadi `RESEND_API_KEY`.

**9. Tentukan pengirim.** `EMAIL_FROM="AYAKA API <noreply@mail.olpistore.com>"`. Domainnya harus sama dengan domain yang sudah diverifikasi.

### Bagian C — Secret

**10. Buat secret acak:**
```bash
python scripts/generate_secrets.py
```
Simpan ketiga nilai yang dihasilkan (`SECRET_KEY`, `API_KEY_PEPPER`, `SESSION_SECRET`) di password manager. **`API_KEY_PEPPER` jangan pernah diganti setelah production berjalan**, karena seluruh API Key yang ada akan menjadi tidak valid.

### Bagian D — GitHub & Vercel

**11. Push ke GitHub.** Buat repository (mis. `olpigiantara-design/ayaka-api`), lalu:
```bash
git init && git add . && git commit -m "AYAKA API v1.0.0"
git branch -M main && git remote add origin https://github.com/olpigiantara-design/ayaka-api.git
git push -u origin main
```
Pastikan `.env` **tidak** ikut ter-push (`.gitignore` sudah menanganinya).

**12. Import ke Vercel.** Buka https://vercel.com/new, pilih repository tersebut, lalu set **Framework Preset: Other**. Build Command dan Output Directory dibiarkan kosong; `vercel.json` sudah mengatur semuanya.

**13. Isi Environment Variables** (Settings → Environment Variables, centang Production, Preview, dan Development):

| Nama | Nilai |
|---|---|
| `DATABASE_URL` | URL pooled Neon dari langkah 2 |
| `BASE_URL` | sementara `https://ayaka-api.vercel.app` (diperbarui di langkah 15) |
| `RESEND_API_KEY` | dari langkah 8 |
| `EMAIL_FROM` | dari langkah 9 |
| `ADMIN_EMAIL` | `olpieditz336@gmail.com` |
| `SECRET_KEY`, `API_KEY_PEPPER`, `SESSION_SECRET` | dari langkah 10 |
| `ENVIRONMENT` | `production` |

**14. Deploy.** Klik **Deploy** dan tunggu hingga status **Ready**. Function `api/index.py` memakai Python 3.12 (`.python-version`).

**15. Set BASE_URL final.** Salin domain production (atau domain kustom dari **Settings → Domains**), perbarui `BASE_URL` tanpa `/` di akhir, lalu buka **Deployments → ⋯ → Redeploy**. `BASE_URL` dipakai di link Magic Link dan reset password, jadi nilainya harus benar.

### Bagian E — Admin & verifikasi

**16. Cek kesehatan.** Buka `https://DOMAIN/api/health`. Hasil yang diharapkan: `"database":{"status":"ok"}` dan `"email_service":"configured"`.

**17. Daftarkan akun owner.** Buka `https://DOMAIN/register` dan daftar dengan `olpieditz336@gmail.com`.

**18. Jadikan admin (Ayaka Sync).** Dari komputer Anda:
```bash
DATABASE_URL="postgresql://...-pooler..." python scripts/create_admin.py olpieditz336@gmail.com
```
Atau lewat Neon SQL Editor:
```sql
INSERT INTO admin_users (user_id, role, display_name, created_by)
SELECT id, 'superadmin', 'Ayaka Sync', 'sql' FROM users WHERE lower(email) = 'olpieditz336@gmail.com'
ON CONFLICT (user_id) DO UPDATE SET role = 'superadmin';
```
Logout, login lagi, lalu buka `https://DOMAIN/admin`.

**19. Uji API Key.** Di Dashboard buka **API Key Manager → Generate API Key**, centang semua permission, lalu salin key-nya (key hanya tampil sekali). Uji dengan:
```bash
curl -H "X-API-Key: ayaka_live_xxx" https://DOMAIN/api/user/profile
```

**20. Uji Magic Link end-to-end.**
```bash
curl -X POST https://DOMAIN/api/am/send -H "X-API-Key: ayaka_live_xxx" -H "Content-Type: application/json" \
     -d '{"email":"email-anda@gmail.com","plan":"premium"}'
```
Buka email yang masuk dan klik **Aktifkan Premium**; halaman verifikasi akan menampilkan *Premium aktif*. Lalu cek:
`curl "https://DOMAIN/api/am/status?email=email-anda@gmail.com" -H "X-API-Key: ayaka_live_xxx"` harus menampilkan `"premium": true`.
Jika gagal, buka **Admin → Monitoring** atau tabel `email_logs` untuk melihat pesan error dari Resend.

**21. Uji admin & maintenance.** Di **Admin → Settings & Maintenance**, aktifkan maintenance. Dari jendela incognito, API mengembalikan `503 MAINTENANCE_MODE` dan halaman publik diarahkan ke `/maintenance`. Matikan lagi setelahnya. Pastikan juga **Audit Logs** mencatat perubahan tersebut. Opsional: tambahkan domain kustom, aktifkan **Vercel Firewall/Attack Challenge**, dan atur *Neon autoscaling* sesuai trafik.

---

## Pemecahan masalah

| Gejala | Penyebab & solusi |
|---|---|
| `500` dan log Vercel berisi `Missing/too-short secrets (min 32 chars)` | Secret belum diisi atau terlalu pendek. Isi ulang lalu redeploy. |
| `/api/health` → `database: error` | `DATABASE_URL` salah, tidak memakai `sslmode=require`, atau project Neon sedang *suspended*. Gunakan URL `-pooler`. |
| `502 EMAIL_DELIVERY_FAILED` | `RESEND_API_KEY`/`EMAIL_FROM` salah atau domain belum Verified. Detail error Resend tersedia di `error.details.provider_error`. |
| Login berhasil tapi langsung keluar | `ENVIRONMENT=production` dibuka lewat `http://`. Cookie `__Host-` hanya berfungsi di HTTPS. Untuk lokal gunakan `ENVIRONMENT=development`. |
| Link Magic Link mengarah ke domain lama | `BASE_URL` belum diperbarui. Ulangi langkah 15. |
| `/admin` diarahkan ke dashboard | Akun belum ada di tabel `admin_users`. Ulangi langkah 18 lalu login ulang. |
