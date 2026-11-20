"""Transactional email templates — AYAKA API yellow/white Neo Brutalism theme.

Email clients ignore external CSS, so styles are inline and table-based.
All dynamic values are HTML-escaped.
"""
from __future__ import annotations

from html import escape

YELLOW = "#FFD600"
BLACK = "#151515"
BG = "#F7F7F2"


def _layout(title: str, greeting: str, intro: str, button_label: str | None, button_url: str | None,
            details: list[tuple[str, str]], security_note: str) -> str:
    rows = "".join(
        f'<tr><td style="padding:6px 0;font:600 13px Arial,sans-serif;color:#555;">{escape(k)}</td>'
        f'<td style="padding:6px 0;font:700 13px Arial,sans-serif;color:{BLACK};text-align:right;">{escape(v)}</td></tr>'
        for k, v in details)
    button = ""
    if button_label and button_url:
        button = (
            f'<tr><td style="padding:8px 0 24px;"><a href="{escape(button_url, quote=True)}" '
            f'style="display:inline-block;background:{YELLOW};color:{BLACK};text-decoration:none;'
            f'font:800 16px Arial,sans-serif;padding:16px 28px;border:3px solid {BLACK};'
            f'border-radius:10px;box-shadow:5px 5px 0 {BLACK};">{escape(button_label)} &rarr;</a></td></tr>'
            f'<tr><td style="font:12px Arial,sans-serif;color:#555;padding-bottom:18px;word-break:break-all;">'
            f'Jika tombol tidak berfungsi, salin tautan ini ke browser:<br>'
            f'<span style="color:{BLACK};">{escape(button_url)}</span></td></tr>')
    return f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>{escape(title)}</title></head>
<body style="margin:0;padding:0;background:{BG};">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{BG};padding:28px 12px;">
<tr><td align="center">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;background:#FFFFFF;border:3px solid {BLACK};border-radius:14px;box-shadow:8px 8px 0 {BLACK};">
<tr><td style="background:{YELLOW};border-bottom:3px solid {BLACK};border-radius:11px 11px 0 0;padding:20px 28px;">
  <span style="display:inline-block;background:{BLACK};color:{YELLOW};font:900 18px Arial,sans-serif;padding:6px 10px;border-radius:6px;letter-spacing:1px;">AYAKA</span>
  <span style="font:900 18px Arial,sans-serif;color:{BLACK};letter-spacing:1px;">&nbsp;API</span>
</td></tr>
<tr><td style="padding:28px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0">
<tr><td style="font:900 26px Arial,sans-serif;color:{BLACK};padding-bottom:12px;text-transform:uppercase;">{escape(title)}</td></tr>
<tr><td style="font:700 15px Arial,sans-serif;color:{BLACK};padding-bottom:8px;">{escape(greeting)}</td></tr>
<tr><td style="font:15px/1.6 Arial,sans-serif;color:#333;padding-bottom:20px;">{escape(intro)}</td></tr>
{button}
<tr><td><table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-top:2px dashed {BLACK};border-bottom:2px dashed {BLACK};margin-bottom:20px;">{rows}</table></td></tr>
<tr><td style="background:#FFF7C2;border:2px solid {BLACK};border-radius:10px;padding:14px;font:13px/1.5 Arial,sans-serif;color:{BLACK};">
<strong>&#128274; Info keamanan:</strong> {escape(security_note)}</td></tr>
</table></td></tr>
<tr><td style="border-top:3px solid {BLACK};padding:16px 28px;font:12px Arial,sans-serif;color:#555;">
Powered by <strong style="color:{BLACK};">AYAKA Sync</strong> &middot; Owner: OLPI STORE<br>
Email otomatis dari AYAKA API — jangan balas email ini.</td></tr>
</table></td></tr></table></body></html>"""


def _text(title: str, intro: str, url: str | None, details: list[tuple[str, str]], note: str) -> str:
    lines = [f"AYAKA API — {title}", "", intro, ""]
    if url:
        lines += [url, ""]
    lines += [f"{k}: {v}" for k, v in details]
    lines += ["", f"Keamanan: {note}", "", "Powered by AYAKA Sync · Owner: OLPI STORE"]
    return "\n".join(lines)


def _greet(name: str | None) -> str:
    return f"Halo {name}," if name else "Halo,"


def magic_link(url: str, email: str, expires_minutes: int, plan: str, name: str | None = None):
    title = "Aktivasi Premium"
    intro = (f"Kami menerima permintaan aktivasi paket {plan.upper()} untuk {email}. "
             f"Klik tombol di bawah untuk memverifikasi akun dan mengaktifkan Premium.")
    details = [("Email", email), ("Paket", plan.upper()), ("Berlaku", f"{expires_minutes} menit"),
               ("Sekali pakai", "Ya")]
    note = ("Tautan ini hanya bisa digunakan satu kali dan kedaluwarsa dalam "
            f"{expires_minutes} menit. Abaikan email ini jika Anda tidak memintanya.")
    return ("Verifikasi akun Premium AYAKA API",
            _layout(title, _greet(name), intro, "Verify Account", url, details, note),
            _text(title, intro, url, details, note))


def premium_activated(email: str, expires_at: str, plan: str):
    title = "Premium Aktif"
    intro = f"Selamat! Paket {plan.upper()} untuk {email} sekarang aktif."
    details = [("Email", email), ("Paket", plan.upper()), ("Aktif hingga", expires_at)]
    note = "Jika Anda tidak melakukan aktivasi ini, segera hubungi penyedia aplikasi Anda."
    return ("Premium Anda telah aktif — AYAKA API", _layout(title, _greet(None), intro, None, None, details, note),
            _text(title, intro, None, details, note))


def premium_renewed(email: str, expires_at: str, days: int):
    title = "Premium Diperpanjang"
    intro = f"Masa berlaku Premium untuk {email} berhasil diperpanjang {days} hari."
    details = [("Email", email), ("Tambahan", f"{days} hari"), ("Aktif hingga", expires_at)]
    note = "Perpanjangan dilakukan oleh aplikasi yang terhubung dengan AYAKA API."
    return ("Premium berhasil diperpanjang — AYAKA API", _layout(title, _greet(None), intro, None, None, details, note),
            _text(title, intro, None, details, note))


def premium_revoked(email: str, reason: str | None):
    title = "Premium Dicabut"
    intro = f"Status Premium untuk {email} telah dicabut."
    details = [("Email", email), ("Alasan", reason or "Tidak disebutkan")]
    note = "Jika menurut Anda ini sebuah kesalahan, hubungi penyedia aplikasi Anda."
    return ("Status Premium dicabut — AYAKA API", _layout(title, _greet(None), intro, None, None, details, note),
            _text(title, intro, None, details, note))


def security_notice(name: str, event: str, when: str, ip: str | None):
    title = "Pemberitahuan Keamanan"
    intro = f"Ada aktivitas keamanan pada akun AYAKA API Anda: {event}."
    details = [("Aktivitas", event), ("Waktu (UTC)", when), ("Jaringan", ip or "Tidak diketahui")]
    note = "Jika ini bukan Anda, segera reset password dan cabut API Key yang mencurigakan."
    return (f"Keamanan akun: {event} — AYAKA API", _layout(title, _greet(name), intro, None, None, details, note),
            _text(title, intro, None, details, note))


def reset_password(name: str, url: str, expires_minutes: int):
    title = "Reset Password"
    intro = "Kami menerima permintaan reset password untuk akun AYAKA API Anda."
    details = [("Berlaku", f"{expires_minutes} menit"), ("Sekali pakai", "Ya")]
    note = "Abaikan email ini jika Anda tidak meminta reset password. Password lama tetap berlaku."
    return ("Reset password AYAKA API", _layout(title, _greet(name), intro, "Reset Password", url, details, note),
            _text(title, intro, url, details, note))
