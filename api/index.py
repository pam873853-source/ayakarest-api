"""Vercel Python Serverless entrypoint. Vercel detects the ASGI `app` object."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from ayaka.main import app  # noqa: E402,F401
