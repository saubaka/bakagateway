from __future__ import annotations

import os
from datetime import timedelta


class BaseConfig:
    APP_NAME = "baka网关"
    APP_NAME_EN = "bakagateway"
    APP_VERSION = "1.13.0"
    SECRET_KEY = os.getenv("CLOUD_GATEWAY_SECRET_KEY")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "connect_args": {"timeout": 5},
        "pool_pre_ping": True,
    }
    SESSION_COOKIE_NAME = "cloudgate_session"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    PERMANENT_SESSION_LIFETIME = timedelta(days=30)
    REMEMBER_COOKIE_NAME = "cloudgate_remember"
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = "Lax"
    WTF_CSRF_TIME_LIMIT = 2 * 60 * 60
    SEND_FILE_MAX_AGE_DEFAULT = 0
    MAX_CONTENT_LENGTH = 2 * 1024 * 1024
    OIDC_ISSUER = os.getenv("CLOUD_GATEWAY_ISSUER", "http://127.0.0.1:5100").rstrip("/")
    ACCESS_TOKEN_TTL = 3600
    REFRESH_TOKEN_TTL = 30 * 24 * 3600
    AUTHORIZATION_CODE_TTL = 180
    SESSION_TTL = 12 * 3600
    PERSISTENT_SESSION_TTL = 30 * 24 * 3600
    LOGIN_LIMIT = 5
    LOGIN_WINDOW_SECONDS = 15 * 60
    ENV_NAME = "production"


class DevelopmentConfig(BaseConfig):
    DEBUG = True
    ENV_NAME = "development"
    SESSION_COOKIE_SECURE = os.getenv("CLOUD_GATEWAY_COOKIE_SECURE", "0") == "1"
    REMEMBER_COOKIE_SECURE = SESSION_COOKIE_SECURE


class LocalConfig(BaseConfig):
    ENV_NAME = "local"
    # start.bat runs with FLASK_DEBUG=0; still reload Jinja templates on each request.
    TEMPLATES_AUTO_RELOAD = True
    SESSION_COOKIE_SECURE = False
    REMEMBER_COOKIE_SECURE = False


class TestingConfig(BaseConfig):
    TESTING = True
    ENV_NAME = "testing"
    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = False
    REMEMBER_COOKIE_SECURE = False


class ProductionConfig(BaseConfig):
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True


CONFIGS = {
    "local": LocalConfig,
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}
