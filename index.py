"""
Vercel serverless entrypoint.

Vercel's Python runtime looks for a WSGI-compatible `app` object in the file
referenced by vercel.json's "src". Rather than duplicating the Flask app, we
just import the real one from backend/app.py and expose it here.
"""
import os
import sys

# Make backend/ importable (backend/app.py, backend/models.py, backend/utils/...)
BACKEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend")
sys.path.insert(0, BACKEND_DIR)

from app import app  # noqa: E402  (the Flask app object from backend/app.py)

# Vercel's Python builder detects this module-level `app` and serves it.
