import uuid
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from flask import Flask, g, request
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import generate_password_hash

from . import models  # noqa: F401
from .config import configuration
from .extensions import db, migrate
from .responses import failure, success

VERSION = "0.7.0"
MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"


def create_app(overrides=None):
    app = Flask(__name__)
    app.config.update(configuration(overrides))
    db.init_app(app)
    migrate.init_app(app, db, directory=str(MIGRATIONS))
    if app.config["BG_TRUST_PROXY"]:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=0, x_host=0, x_port=0, x_prefix=0)
    app.config["BG_DUMMY_HASH"] = generate_password_hash(
        "not-a-real-account", method="scrypt:131072:8:1"
    )
    from .auth.cli import register
    from .auth.routes import bp, csrf, options
    from .auth.security import AuthError

    app.register_blueprint(bp)
    from .account.avatars import cleanup_command
    from .account.routes import bp as account_bp

    app.register_blueprint(account_bp)
    app.cli.add_command(cleanup_command)
    from .oauth.cli import register as register_oauth
    from .oauth.keys import initialize as initialize_keys
    from .oauth.routes import bp as oauth_bp
    from .oauth.server import initialize

    initialize(app)
    app.register_blueprint(oauth_bp)
    app.cli.add_command(initialize_keys)
    register_oauth(app)
    register(app)
    from .admin.routes import bp as admin_bp
    from .admin.routes import public_bp, site_view

    app.register_blueprint(admin_bp)
    app.register_blueprint(public_bp)

    @app.before_request
    def identify_request():
        g.request_id = uuid.uuid4().hex
        if request.method == "POST" and (
            request.path == "/api/account/avatar"
            or (request.path.startswith("/api/admin/clients/") and request.path.endswith("/icon"))
        ):
            request.max_content_length = 3 * 1024 * 1024

    @app.after_request
    def headers(response):
        response.headers.update(
            {
                "X-Request-ID": g.request_id,
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "same-origin",
            }
        )
        return response

    def readiness():
        try:
            db.session.execute(text("SELECT 1"))
            alembic = Config()
            alembic.set_main_option("script_location", str(MIGRATIONS))
            expected = ScriptDirectory.from_config(alembic).get_current_head()
            actual = db.session.execute(text("SELECT version_num FROM alembic_version")).scalar()
            label = db.session.execute(
                text("SELECT schema_label FROM platform_installation WHERE id = 1")
            ).scalar()
            if actual != expected or label != "p1-foundation":
                return failure("schema_not_ready", "数据库结构尚未就绪。", 503)
            from .oauth.keys import private_key

            try:
                private_key()
            except (OSError, ValueError, KeyError):
                return failure("signing_key_unavailable", "身份签名配置尚未就绪。", 503)
            return success({"database": "postgresql", "migration": actual, "ready": True})
        except SQLAlchemyError as error:
            db.session.rollback()
            # SQLSTATE only: database errors can include URLs, SQL and parameters.
            sqlstate = getattr(getattr(error, "orig", None), "sqlstate", None)
            if sqlstate in {"42P01", "3F000"}:
                return failure("schema_not_ready", "请先完成数据库迁移。", 503)
            return failure("database_unavailable", "暂时无法连接数据库，请稍后重试。", 503)

    @app.get("/api/health/live")
    def live():
        return success({"status": "alive", "version": VERSION})

    @app.get("/api/health/ready")
    def ready():
        return readiness()

    @app.get("/api/system")
    def system():
        return success(
            {
                **site_view(),
                "version": VERSION,
                "capabilities": {"authentication": True, **options()},
            }
        )

    @app.post("/api/system/check")
    def check():
        csrf()
        if not request.is_json:
            return failure("unsupported_media_type", "此请求需要 JSON 格式。", 415)
        if request.get_json() != {}:
            return failure("invalid_request", "请求内容不符合接口约定。", 400)
        return readiness()

    @app.errorhandler(AuthError)
    def auth_error(error):
        db.session.rollback()
        response, status = failure(error.code, error.message, error.status)
        if error.retry_after:
            response.headers["Retry-After"] = str(error.retry_after)
        return response, status

    @app.errorhandler(SQLAlchemyError)
    def database_error(error):
        db.session.rollback()
        return failure("database_unavailable", "数据库暂不可用，请稍后重试。", 503)

    @app.errorhandler(HTTPException)
    def http_error(error):
        codes = {
            400: "invalid_request",
            404: "not_found",
            405: "method_not_allowed",
            413: "request_too_large",
            415: "unsupported_media_type",
        }
        return failure(
            codes.get(error.code, "request_failed"), "请求无法处理或功能尚未提供。", error.code
        )

    @app.errorhandler(Exception)
    def internal_error(error):
        app.logger.error("request_failed request_id=%s type=%s", g.request_id, type(error).__name__)
        return failure("internal_error", "服务暂时不可用，请稍后重试。", 500)

    return app
