#!/usr/bin/env python3
"""Print strong random values for SECRET_KEY, API_KEY_PEPPER, SESSION_SECRET (paste into Vercel env)."""
import secrets

for name in ("SECRET_KEY", "API_KEY_PEPPER", "SESSION_SECRET"):
    print(f"{name}={secrets.token_urlsafe(48)}")
