#!/usr/bin/env python3
"""Apply database/migrations/*.sql to the database in DATABASE_URL (idempotent).

Usage:
    DATABASE_URL="postgresql://...neon.tech/neondb?sslmode=require" python scripts/migrate.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "database" / "migrations"


def main() -> int:
    url = os.getenv("DATABASE_URL")
    if not url:
        print("ERROR: DATABASE_URL belum diatur.", file=sys.stderr)
        return 1
    files = sorted(MIGRATIONS.glob("*.sql"))
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS schema_migrations (
                          version VARCHAR(64) PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())""")
        done = {r[0] for r in conn.execute("SELECT version FROM schema_migrations").fetchall()}
        for f in files:
            version = f.stem
            if version in done:
                print(f"= {version} (sudah diterapkan)")
                continue
            print(f"+ menerapkan {version} …")
            with conn.transaction():
                conn.execute(f.read_text(encoding="utf-8"))
                conn.execute("INSERT INTO schema_migrations (version) VALUES (%s) ON CONFLICT DO NOTHING", (version,))
        tables = conn.execute("""SELECT count(*) FROM information_schema.tables
                                  WHERE table_schema='public' AND table_type='BASE TABLE'""").fetchone()[0]
    print(f"Selesai. {tables} tabel tersedia.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
