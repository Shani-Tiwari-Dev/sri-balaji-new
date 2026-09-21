"""
Django settings for the Sri Balaji Granites & Marbles project.

This replaces the old Flask `backend/config.py`. Every environment variable
name is kept identical to the Flask version so existing `.env` files /
hosting-provider env vars keep working unchanged.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent          # backend_django/
PROJECT_ROOT = BASE_DIR.parent                              # repo root
FRONTEND_DIR = PROJECT_ROOT / "frontend"

SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"

ALLOWED_HOSTS = ["*"]  # the API is designed to be safe behind any hostname; tighten in production if you like

INSTALLED_APPS = [
    "django.contrib.staticfiles",
    "corsheaders",
    "catalog",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "sbg.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": []},
    },
]

WSGI_APPLICATION = "sbg.wsgi.application"

# ---------------------------------------------------------------------------
# Database — same fallback behaviour as the Flask app: use DATABASE_URL
# (Supabase/Postgres) if set, otherwise fall back to a local SQLite file so
# the app runs out of the box. On Vercel the code directory is read-only, so
# SQLite is pointed at /tmp there (same caveat as before: /tmp is wiped on
# every cold start — use Postgres for anything that needs to persist).
# ---------------------------------------------------------------------------
import dj_database_url  # noqa: E402

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
if DATABASE_URL:
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    DATABASES = {"default": dj_database_url.parse(DATABASE_URL, conn_max_age=0 if os.environ.get("VERCEL") else 600)}
else:
    db_dir = Path("/tmp") if os.environ.get("VERCEL") else BASE_DIR
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": db_dir / "sri_balaji_local.db",
        }
    }

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# All the app's own timestamp handling (catalog/models.py: gen_id/iso_z/
# make_trash_expiry) works in aware UTC datetimes, matching the old Flask
# app's utcnow()-based scheme — so tell Django to store/return aware UTC
# datetimes too (its default is naive local time, which would silently
# disagree with our own helpers).
USE_TZ = True
TIME_ZONE = "UTC"
LANGUAGE_CODE = "en-us"

# ---------------------------------------------------------------------------
# Static files — the frontend (plain HTML/CSS/JS, no build step) is served
# straight out of frontend/, exactly like the old Flask `static_folder`.
# ---------------------------------------------------------------------------
STATIC_URL = "/static/"
STATICFILES_DIRS = [FRONTEND_DIR] if FRONTEND_DIR.exists() else []
STATIC_ROOT = BASE_DIR / "staticfiles_collected"
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# ---------------------------------------------------------------------------
# Media files — real uploaded slab photos live here now (see catalog/models
# .py: Slab.image). This is the fix for both the "photo update" bug and the
# slow-loading problem: photos are stored as real files served by URL,
# instead of being base64-encoded and stuffed into every /api/slabs JSON
# response.
# ---------------------------------------------------------------------------
MEDIA_URL = "/media/"
MEDIA_ROOT = Path("/tmp/media") if os.environ.get("VERCEL") else (BASE_DIR / "media")

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
_cors_origins = os.environ.get("CORS_ORIGINS", "*").strip()
if _cors_origins == "*":
    CORS_ALLOW_ALL_ORIGINS = True
else:
    CORS_ALLOWED_ORIGINS = [o.strip() for o in _cors_origins.split(",") if o.strip()]

# ---------------------------------------------------------------------------
# App-specific settings (read by catalog/auth.py, catalog/views.py)
# ---------------------------------------------------------------------------
JWT_EXPIRY_HOURS = int(os.environ.get("JWT_EXPIRY_HOURS", "12"))

STAFF_PASSWORDS = [
    p.strip() for p in os.environ.get(
        "STAFF_PASSWORDS",
        "Shayam@123,admin@123,pass123,g1@123,g2@123,g3@123,123456",
    ).split(",") if p.strip()
]

WHATSAPP_NUMBER = os.environ.get("WHATSAPP_NUMBER", "919828400811")
WHATSAPP_NUMBER_SECONDARY = os.environ.get("WHATSAPP_NUMBER_SECONDARY", "919982749180")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")

# Max upload size for a single slab photo (10 MB — phone camera photos land
# well under this; Slab.save() will still reject non-images).
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
