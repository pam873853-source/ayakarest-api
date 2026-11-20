#!/usr/bin/env python3
"""Promote an EXISTING registered user to administrator (role stored in admin_users).

The admin role is never derived from an email address at runtime — it only exists
after this script (or the equivalent SQL) has been run by the project owner.

Usage:
    DATABASE_URL="postgresql://..." python scripts/create_admin.py olpieditz336@gmail.com [--role superadmin]
    DATABASE_URL="postgresql://..." python scripts/create_admin.py olpieditz336@gmail.com --remove
"""
from __future__ import annotations

import argparse
import os
import sys

import psycopg


def main() -> int:
    ap = argparse.ArgumentParser(description="Kelola admin AYAKA API")
    ap.add_argument("email", nargs="?", default=os.getenv("ADMIN_EMAIL", "olpieditz336@gmail.com"))
    ap.add_argument("--role", choices=["admin", "superadmin"], default="superadmin")
    ap.add_argument("--remove", action="store_true", help="Cabut hak admin")
    args = ap.parse_args()
    url = os.getenv("DATABASE_URL")
    if not url:
        print("ERROR: DATABASE_URL belum diatur.", file=sys.stderr)
        return 1
    with psycopg.connect(url, autocommit=True) as conn:
        row = conn.execute("SELECT id, username FROM users WHERE lower(email) = lower(%s)", (args.email,)).fetchone()
        if not row:
            print(f"ERROR: belum ada akun dengan email {args.email}. Register dulu di /register.", file=sys.stderr)
            return 2
        uid, username = row
        if args.remove:
            conn.execute("DELETE FROM admin_users WHERE user_id = %s", (uid,))
            conn.execute("""INSERT INTO audit_logs (actor_type, actor_id, action, target_type, target_id, user_id)
                            VALUES ('system', 'cli', 'admin.removed', 'user', %s, %s)""", (str(uid), uid))
            print(f"Hak admin {args.email} dicabut.")
            return 0
        conn.execute("""INSERT INTO admin_users (user_id, role, display_name, created_by)
                        VALUES (%s, %s, 'Ayaka Sync', 'cli')
                        ON CONFLICT (user_id) DO UPDATE SET role = EXCLUDED.role""", (uid, args.role))
        conn.execute("""INSERT INTO audit_logs (actor_type, actor_id, action, target_type, target_id, user_id, metadata)
                        VALUES ('system', 'cli', 'admin.granted', 'user', %s, %s, jsonb_build_object('role', %s::text))""",
                     (str(uid), uid, args.role))
    print(f"OK: {args.email} (@{username}) sekarang {args.role} — tampil sebagai 'Ayaka Sync'. Login lalu buka /admin.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
