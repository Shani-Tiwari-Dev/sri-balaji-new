import os
from dotenv import load_dotenv
from sqlalchemy.pool import NullPool

load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


def _database_uri():
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        # Local fallback so the app runs out-of-the-box without Supabase configured.
        return "sqlite:///" + os.path.join(BASE_DIR, "sri_balaji_local.db")
    # SQLAlchemy 2.x wants postgresql:// not postgres://
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return url


class Config:
    SQLALCHEMY_DATABASE_URI = _database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # Serverless platforms (Vercel) spin up a fresh process per request/cold
    # start, so a persistent connection pool just accumulates dead
    # connections against Supabase's connection limit. NullPool opens a
    # connection per request and closes it right after — the right model
    # for this environment. pool_pre_ping guards against the odd stale
    # connection on traditional long-running hosts (Option A).
    if os.environ.get("VERCEL"):
        SQLALCHEMY_ENGINE_OPTIONS = {"poolclass": NullPool}
    else:
        SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")
    JWT_EXPIRY_HOURS = int(os.environ.get("JWT_EXPIRY_HOURS", "12"))

    STAFF_PASSWORDS = [
        p.strip() for p in os.environ.get(
            "STAFF_PASSWORDS",
            "Shayam@123,admin@123,pass123,g1@123,g2@123,g3@123,123456",
        ).split(",") if p.strip()
    ]

    WHATSAPP_NUMBER = os.environ.get("WHATSAPP_NUMBER", "919828400811")
    WHATSAPP_NUMBER_SECONDARY = os.environ.get("WHATSAPP_NUMBER_SECONDARY", "919982749180")

    CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "*")

    SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
    SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
