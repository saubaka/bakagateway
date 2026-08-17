from __future__ import annotations

import os
import secrets
import stat
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import click
from flask import Flask, render_template, request, session
from flask_login import current_user, logout_user
from sqlalchemy import event
from sqlalchemy.engine import Engine

from app.config import CONFIGS
from app.extensions import csrf, db, login_manager, migrate
from app.logging_filters import install_werkzeug_sensitive_query_filter
from app.models import GatewayClient, User
from app.security import ensure_signing_keys, new_token
from app.services.appearance import load_footer_content, load_theme_settings
from app.services.auth import administrator_exists, current_gateway_session, seed_roles
from app.services.local_recovery import create_local_recovery_token


@event.listens_for(Engine, "connect")
def configure_sqlite(connection, _record):
    if connection.__class__.__module__.startswith("sqlite3"):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()


def _load_or_create_secret(app: Flask) -> None:
    configured = str(app.config.get("SECRET_KEY") or "").strip()
    if configured:
        if len(configured) < 32:
            raise RuntimeError("CLOUD_GATEWAY_SECRET_KEY must contain at least 32 characters.")
        app.config["SECRET_KEY"] = configured
        return

    secret_path = Path(app.instance_path) / "cloudgate-secret.key"
    try:
        secret = secret_path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        secret = secrets.token_urlsafe(48)
        try:
            with secret_path.open("x", encoding="utf-8") as handle:
                handle.write(secret)
        except FileExistsError:
            secret = secret_path.read_text(encoding="utf-8").strip()
        with suppress(OSError):
            secret_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    if len(secret) < 32:
        raise RuntimeError("The persisted bakagateway secret is invalid.")
    app.config["SECRET_KEY"] = secret


def _validate_security_config(app: Flask) -> None:
    if app.testing or app.config.get("ENV_NAME") != "production":
        return
    issuer = urlsplit(app.config["OIDC_ISSUER"])
    if issuer.scheme != "https" or not issuer.netloc:
        raise RuntimeError("Production mode requires a complete HTTPS CLOUD_GATEWAY_ISSUER.")
    if not (
        app.config.get("SESSION_COOKIE_SECURE")
        and app.config.get("REMEMBER_COOKIE_SECURE")
    ):
        raise RuntimeError("Production mode requires secure authentication cookies.")


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    environment = os.getenv("CLOUD_GATEWAY_ENV", "local").strip().lower()
    if environment not in CONFIGS:
        raise RuntimeError(f"Unknown CLOUD_GATEWAY_ENV: {environment}")
    app.config.from_object(CONFIGS[environment])
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    database_override = os.getenv("CLOUD_GATEWAY_DATABASE")
    if database_override:
        database_path = Path(database_override).resolve()
    else:
        database_path = Path(app.instance_path) / "cloudgate.db"
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{database_path.as_posix()}"
    if test_config:
        app.config.update(test_config)
    _load_or_create_secret(app)
    _validate_security_config(app)
    install_werkzeug_sensitive_query_filter()

    private_key, public_key = ensure_signing_keys(app.instance_path)
    app.config["OIDC_PRIVATE_KEY"] = str(private_key)
    app.config["OIDC_PUBLIC_KEY"] = str(public_key)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "请先登录，再继续访问。"
    login_manager.login_message_category = "info"

    from app.blueprints.admin import admin_bp
    from app.blueprints.auth import auth_bp
    from app.blueprints.oauth import oauth_bp
    from app.blueprints.portal import portal_bp

    app.register_blueprint(portal_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(oauth_bp)
    app.register_blueprint(admin_bp)

    @login_manager.user_loader
    def load_user(user_id: str):
        try:
            user = db.session.get(User, int(user_id))
        except (TypeError, ValueError):
            return None
        if user is None or not user.is_active:
            return None
        if request.endpoint and request.endpoint.startswith("static"):
            return user
        return user if current_gateway_session() is not None else None

    @app.before_request
    def maintain_session():
        if not current_user.is_authenticated:
            return None
        item = current_gateway_session()
        if item is None:
            logout_user()
            session.clear()
            return None
        now = datetime.now(UTC)
        last_seen = item.last_seen_at
        if last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=UTC)
        if now - last_seen > timedelta(minutes=2):
            item.last_seen_at = now
            db.session.commit()
        return None

    @app.after_request
    def security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()"
        )
        form_action = "'self'"
        image_sources = "'self' data: blob:"
        oauth_client = None
        if request.endpoint == "oauth.authorize":
            client_id = request.values.get("client_id", "")
            redirect_uri = request.values.get("redirect_uri", "")
            oauth_client = db.session.scalar(
                db.select(GatewayClient).where(
                    GatewayClient.client_id == client_id,
                    GatewayClient.is_active.is_(True),
                )
            )
            if oauth_client is not None and redirect_uri in oauth_client.redirect_uris:
                target = urlsplit(redirect_uri)
                if target.scheme in {"http", "https"} and target.netloc:
                    form_action += f" {target.scheme}://{target.netloc}"
        elif request.endpoint in {"auth.login", "auth.register", "auth.two_factor"}:
            next_target = request.args.get("next") or session.get("login_next", "")
            parts = urlsplit(next_target)
            if parts.path.rstrip("/") == "/oauth/authorize":
                client_id = parse_qs(parts.query).get("client_id", [""])[0]
                oauth_client = db.session.scalar(
                    db.select(GatewayClient).where(
                        GatewayClient.client_id == client_id,
                        GatewayClient.is_active.is_(True),
                    )
                )
        if oauth_client is not None and oauth_client.icon_url:
            icon_target = urlsplit(oauth_client.icon_url)
            if icon_target.scheme in {"http", "https"} and icon_target.netloc:
                image_sources += f" {icon_target.scheme}://{icon_target.netloc}"
        if request.endpoint in {"portal.platforms", "admin.clients", "admin.client_detail"}:
            for icon_url in db.session.scalars(
                db.select(GatewayClient.icon_url).where(
                    GatewayClient.is_active.is_(True),
                    GatewayClient.icon_url != "",
                )
            ):
                icon_target = urlsplit(icon_url)
                source = (
                    f"{icon_target.scheme}://{icon_target.netloc}"
                    if icon_target.scheme in {"http", "https"} and icon_target.netloc
                    else ""
                )
                if source and source not in image_sources:
                    image_sources += f" {source}"
        response.headers.setdefault(
            "Content-Security-Policy",
            f"default-src 'self'; img-src {image_sources}; style-src 'self'; "
            "script-src 'self'; font-src 'self'; connect-src 'self'; "
            f"frame-ancestors 'none'; base-uri 'self'; form-action {form_action}",
        )
        if app.config.get("SESSION_COOKIE_SECURE"):
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return response

    @app.context_processor
    def global_context():
        return {
            "app_name": app.config["APP_NAME"],
            "app_name_en": app.config["APP_NAME_EN"],
            "app_version": app.config["APP_VERSION"],
            "current_year": datetime.now(UTC).year,
            "footer_content": load_footer_content(),
            "theme_settings": load_theme_settings(),
        }

    @app.errorhandler(400)
    def bad_request(_error):
        return render_template("errors/error.html", code=400, title="请求没有通过检查"), 400

    @app.errorhandler(401)
    def unauthorized(_error):
        return render_template("errors/error.html", code=401, title="请先完成登录"), 401

    @app.errorhandler(403)
    def forbidden(_error):
        return render_template("errors/error.html", code=403, title="暂时没有访问权限"), 403

    @app.errorhandler(404)
    def not_found(_error):
        return render_template("errors/error.html", code=404, title="没有找到这个入口"), 404

    @app.errorhandler(500)
    def server_error(_error):
        db.session.rollback()
        return render_template("errors/error.html", code=500, title="网关暂时打了个盹"), 500

    register_commands(app)
    return app


def register_commands(app: Flask) -> None:
    @app.cli.command("init-db")
    def init_db():
        db.create_all()
        seed_roles()
        db.session.commit()
        click.echo("bakagateway database initialized.")

    @app.cli.command("local-recovery-link")
    def local_recovery_link():
        if not administrator_exists():
            click.echo(
                "RECOVERY_URL="
                "http://127.0.0.1:5100/auth/setup/administrator/"
            )
            return
        raw_token = create_local_recovery_token()
        click.echo(
            "RECOVERY_URL="
            f"http://127.0.0.1:5100/auth/recovery/local/{raw_token}/"
        )

    @app.cli.command("create-admin")
    @click.option("--username", prompt=True)
    @click.option("--email", prompt=True)
    @click.option("--display-name", prompt=True)
    @click.password_option()
    def create_admin(username: str, email: str, display_name: str, password: str):
        db.create_all()
        _member, administrator = seed_roles()
        normalized = username.strip().lower()
        if db.session.scalar(db.select(User).where(User.username == normalized)):
            raise click.ClickException("Username already exists.")
        user = User(
            username=normalized,
            email=email.strip().lower(),
            display_name=display_name.strip(),
            email_verified=True,
            status="inactive",
            roles=[administrator],
        )
        user.set_password(password)
        db.session.add(user)
        db.session.flush()
        user.status = "active"
        db.session.flush()
        db.session.commit()
        click.echo(f"Administrator {normalized} created.")

    @app.cli.command("create-client")
    @click.option("--name", prompt=True)
    @click.option("--homepage", prompt=True)
    @click.option("--redirect-uri", prompt=True)
    def create_client(name: str, homepage: str, redirect_uri: str):
        db.create_all()
        raw_secret = new_token(32)
        item = GatewayClient(
            client_id=new_token(18),
            name=name.strip(),
            description="",
            homepage_url=homepage.strip(),
            scopes="openid profile email avatar",
        )
        item.redirect_uris = [redirect_uri.strip()]
        item.set_secret(raw_secret)
        db.session.add(item)
        db.session.commit()
        click.echo(f"client_id={item.client_id}")
        click.echo(f"client_secret={raw_secret}")

    @app.cli.command("purge-email-security")
    def purge_email_security():
        from app.services.email_security import purge_expired_email_security_records

        result = purge_expired_email_security_records()
        db.session.commit()
        click.echo(
            "purged "
            f"email_challenges={result['email_challenges']} "
            f"pending_registrations={result['pending_registrations']} "
            f"pending_email_changes={result['pending_email_changes']}"
        )
