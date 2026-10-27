"""Application configuration, driven by environment variables."""
import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name, default):
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


class Config:
    # No default: the app refuses to start without a real secret key.
    SECRET_KEY = os.environ.get("SECRET_KEY")

    # None means "use instance/sdrn.sqlite" (resolved in create_app).
    DATABASE = os.environ.get("DATABASE_PATH") or None

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _env_bool("SESSION_COOKIE_SECURE", False)
    PERMANENT_SESSION_LIFETIME = timedelta(hours=_env_int("SESSION_HOURS", 8))

    # CSRF tokens stay valid for the whole session.
    WTF_CSRF_TIME_LIMIT = None
