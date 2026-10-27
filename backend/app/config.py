import os
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlsplit

from sqlalchemy import URL


def secret(name):
    file = os.getenv(name + "_FILE")
    return Path(file).read_text().strip() if file else os.getenv(name, "")


def configuration(overrides=None):
    environment = os.getenv("BG_ENV", "local")
    password = secret("BG_DATABASE_PASSWORD")
    uri = os.getenv("BG_DATABASE_URL")
    if not uri and password:
        uri = URL.create(
            "postgresql+psycopg",
            username=os.getenv("BG_DATABASE_USER", "bakagateway"),
            password=password,
            host=os.getenv("BG_DATABASE_HOST", "db"),
            port=int(os.getenv("BG_DATABASE_PORT", "5432")),
            database=os.getenv("BG_DATABASE_NAME", "bakagateway"),
        )
    config = {
        "BG_ENV": environment,
        "SECRET_KEY": secret("BG_SECRET_KEY"),
        "SQLALCHEMY_DATABASE_URI": uri,
        "SQLALCHEMY_TRACK_MODIFICATIONS": False,
        "SQLALCHEMY_ENGINE_OPTIONS": {
            "pool_pre_ping": True,
            "connect_args": {"connect_timeout": 3},
        },
        "SESSION_COOKIE_NAME": "bg_session",
        "SESSION_COOKIE_HTTPONLY": True,
        "SESSION_COOKIE_SAMESITE": "Lax",
        "SESSION_COOKIE_SECURE": environment == "production",
        "PERMANENT_SESSION_LIFETIME": timedelta(days=30),
        "SESSION_REFRESH_EACH_REQUEST": False,
        "BG_TRUST_PROXY": os.getenv("BG_TRUST_PROXY", "0") == "1",
        "TRUSTED_HOSTS": os.getenv("BG_ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]").split(","),
        "MAX_CONTENT_LENGTH": 64 * 1024,
        "BG_UPLOAD_DIR": os.getenv("BG_UPLOAD_DIR", "/app/data/avatars"),
        "BG_SIGNING_KEY_DIR": os.getenv("BG_SIGNING_KEY_DIR", "/app/keys"),
        "BG_PUBLIC_URL": os.getenv("BG_PUBLIC_URL", "http://localhost:5180"),
    }
    config.update(overrides or {})
    if len(config["SECRET_KEY"]) < 32:
        raise ValueError("BG_SECRET_KEY_FILE must contain at least 32 characters")
    value = config["SQLALCHEMY_DATABASE_URI"]
    if not value or not str(value).startswith("postgresql"):
        raise ValueError("A PostgreSQL database configuration is required")
    if config["BG_ENV"] not in {"local", "production", "test"}:
        raise ValueError("BG_ENV must be local, test or production")
    origin = urlsplit(config["BG_PUBLIC_URL"])
    if (
        not origin.hostname
        or origin.username
        or origin.password
        or origin.path not in {"", "/"}
        or origin.query
        or origin.fragment
    ):
        raise ValueError(
            "BG_PUBLIC_URL must be an origin without path, credentials, query or fragment"
        )
    if config["BG_ENV"] == "production":
        if not config["BG_PUBLIC_URL"].startswith("https://"):
            raise ValueError("Production requires an HTTPS public URL")
        if not config["SESSION_COOKIE_SECURE"]:
            raise ValueError("Production requires secure cookies")
    return config
