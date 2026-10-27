import secrets
from functools import wraps

from flask import Blueprint, g, request, send_file
from sqlalchemy import func, or_, text
from werkzeug.security import check_password_hash

from ..account import avatars
from ..auth import mail, sessions
from ..auth.routes import csrf
from ..auth.security import AuthError, digest, email, limit, require_json
from ..extensions import db
from ..models import AdminAudit, AuthSettings, MailConfiguration, SiteSettings, User
from ..oauth.cli import invalidate
from ..oauth.models import OAuthClient, OAuthConsent
from ..oauth.service import SCOPES, web_url
from ..responses import success

bp = Blueprint("admin", __name__, url_prefix="/api/admin")
public_bp = Blueprint("public_apps", __name__)


def invalid(message="请求内容不正确，请检查后重试。"):
    raise AuthError("invalid_request", message)


def fields(data, allowed):
    if set(data) - set(allowed) - {"currentPassword", "expectedVersion"}:
        invalid()


def admin(*, write=False):
    def decorate(fn):
        @wraps(fn)
        def wrapped(**values):
            # Before every User/Session lock. Two administrators cannot deadlock
            # by each locking themselves and then attempting to modify the other.
            if write:
                db.session.execute(text("SELECT pg_advisory_xact_lock(782341)"))
            row = sessions.load(lock=True)
            if not row or not row.user:
                raise AuthError("authentication_required", "请先登录。", 401)
            if row.user.role != "admin":
                raise AuthError("admin_required", "此页面仅限管理员使用。", 403)
            g.auth_session = row
            if write:
                csrf()
                data = require_json()
                limit("admin-reauth", row.user_id, maximum=60, seconds=900)
                value = data.get("currentPassword")
                if (
                    not isinstance(value, str)
                    or len(value) > 128
                    or not check_password_hash(row.user.password_hash, value)
                ):
                    raise AuthError("reauthentication_failed", "当前密码不正确，请重新确认。", 401)
                result = fn(data, **values)
            else:
                result = fn(**values)
            sessions.touch(row)
            db.session.commit()
            return success(result)

        return wrapped

    return decorate


def audit(action, summary, target=""):
    user = g.auth_session.user
    db.session.add(
        AdminAudit(
            actor_id=user.id,
            actor_name=user.username,
            action=action,
            target_id=target,
            summary=summary,
        )
    )


def audit_view(row):
    return {
        "id": row.id,
        "actorId": row.actor_id,
        "actorName": row.actor_name,
        "action": row.action,
        "targetId": row.target_id,
        "summary": row.summary,
        "createdAt": row.created_at.isoformat(),
    }


def pagination(query, model, view):
    try:
        page = int(request.args.get("page", "1"))
        size = int(request.args.get("pageSize", "20"))
        if page < 1 or page > 1000000 or not 1 <= size <= 100:
            invalid()
    except (TypeError, ValueError):
        invalid()
    total = db.session.scalar(db.select(func.count()).select_from(query.subquery()))
    rows = db.session.scalars(
        query.order_by(model.created_at.desc(), model.id.desc())
        .offset((page - 1) * size)
        .limit(size)
    )
    return {"items": [view(row) for row in rows], "total": total, "page": page, "pageSize": size}


def filters(query, model, columns):
    needle = request.args.get("q", "").strip()
    status = request.args.get("status", "all")
    if len(needle) > 80 or status not in {"all", "active", "inactive"}:
        invalid()
    if needle:
        query = query.where(or_(*(column.icontains(needle, autoescape=True) for column in columns)))
    if status != "all":
        field = model.is_active if model is User else model.active
        query = query.where(field.is_(status == "active"))
    return query


def user_view(row):
    return {
        "id": row.id,
        "username": row.username,
        "nickname": row.nickname,
        "email": row.email,
        "role": row.role,
        "active": row.is_active,
        "version": row.auth_version,
        "createdAt": row.created_at.isoformat(),
    }


def client_view(row):
    return {
        "id": row.id,
        "name": row.name,
        "description": row.description,
        "homepage": row.homepage,
        "privacyUrl": row.privacy_url,
        "termsUrl": row.terms_url,
        "redirectUris": row.redirect_uris,
        "scopes": row.scopes.split(),
        "active": row.active,
        "version": row.version,
        "iconUrl": icon_url(row),
        "createdAt": row.created_at.isoformat(),
    }


def icon_url(row):
    return f"/api/apps/{row.id}/icon/{row.icon_key}" if row.icon_key else None


def version(data, actual):
    if type(data.get("expectedVersion")) is not int:
        invalid("请刷新页面后重新提交。")
    if data["expectedVersion"] != actual:
        raise AuthError("conflict", "内容已被其他操作修改，请刷新后重新编辑。", 409)


def locked(model, identifier):
    row = db.session.scalar(
        db.select(model)
        .where(model.id == identifier)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if not row:
        raise AuthError("not_found", "记录不存在。", 404)
    return row


@bp.get("/overview")
@admin()
def overview():
    def count(model, *where):
        return db.session.scalar(db.select(func.count()).select_from(model).where(*where))

    connections = db.session.scalar(
        db.select(func.count())
        .select_from(OAuthConsent)
        .join(User, User.id == OAuthConsent.user_id)
        .join(OAuthClient, OAuthClient.id == OAuthConsent.client_id)
        .where(
            OAuthConsent.revoked_at.is_(None),
            User.is_active.is_(True),
            OAuthClient.active.is_(True),
        )
    )
    return {
        "counts": {
            "users": count(User),
            "activeUsers": count(User, User.is_active.is_(True)),
            "admins": count(User, User.role == "admin", User.is_active.is_(True)),
            "clients": count(OAuthClient),
            "activeClients": count(OAuthClient, OAuthClient.active.is_(True)),
            "connections": connections,
        },
        "recent": [
            audit_view(row)
            for row in db.session.scalars(
                db.select(AdminAudit)
                .order_by(AdminAudit.created_at.desc(), AdminAudit.id.desc())
                .limit(10)
            )
        ],
    }


@bp.get("/users")
@admin()
def users():
    query = filters(db.select(User), User, [User.username, User.nickname, User.email])
    role = request.args.get("role", "all")
    if role not in {"all", "admin", "user"}:
        invalid()
    if role != "all":
        query = query.where(User.role == role)
    return pagination(query, User, user_view)


@bp.post("/users/<identifier>")
@admin(write=True)
def update_user(data, identifier):
    fields(data, {"active", "role"})
    if type(data.get("active")) is not bool or data.get("role") not in ("admin", "user"):
        invalid()
    row = locked(User, identifier)
    version(data, row.auth_version)
    if row.is_active and row.role == "admin" and (not data["active"] or data["role"] != "admin"):
        others = db.session.scalar(
            db.select(func.count())
            .select_from(User)
            .where(User.is_active.is_(True), User.role == "admin", User.id != row.id)
        )
        if not others:
            raise AuthError("last_admin", "至少保留一位启用的管理员。", 409)
    changed = row.is_active != data["active"] or row.role != data["role"]
    if changed:
        row.is_active, row.role = data["active"], data["role"]
        sessions.revoke_user(row)
        audit("user.update", "修改账号状态或角色，并撤销旧凭据", row.id)
    return {
        "user": user_view(row),
        "sessionInvalidated": changed and row.id == g.auth_session.user_id,
    }


@bp.get("/clients")
@admin()
def clients():
    query = filters(db.select(OAuthClient), OAuthClient, [OAuthClient.name, OAuthClient.id])
    return pagination(query, OAuthClient, client_view)


def client_data(data):
    fields(
        data,
        {
            "name",
            "description",
            "homepage",
            "privacyUrl",
            "termsUrl",
            "redirectUris",
            "scopes",
            "active",
        },
    )
    result = {}
    for source, dest, maximum, required in [
        ("name", "name", 80, True),
        ("description", "description", 240, False),
        ("homepage", "homepage", 512, False),
        ("privacyUrl", "privacy_url", 512, False),
        ("termsUrl", "terms_url", 512, False),
    ]:
        value = data.get(source, "")
        if (
            not isinstance(value, str)
            or len(value.strip()) > maximum
            or (required and not value.strip())
            or any(ord(c) < 32 and c not in "\n\t" for c in value)
        ):
            invalid()
        result[dest] = value.strip()
    scopes = data.get("scopes")
    redirects = data.get("redirectUris")
    if (
        not isinstance(scopes, list)
        or not all(isinstance(x, str) for x in scopes)
        or not set(scopes) <= SCOPES
        or "openid" not in scopes
        or not isinstance(redirects, list)
        or not 1 <= len(redirects) <= 10
        or not all(isinstance(x, str) for x in redirects)
    ):
        invalid("请填写有效返回地址和资料范围。")
    try:
        result["redirect_uris"] = list(dict.fromkeys(web_url(url) for url in redirects))
        for key in ["homepage", "privacy_url", "terms_url"]:
            result[key] = web_url(result[key], optional=True)
    except ValueError:
        invalid("网址不可用：生产使用HTTPS，开发HTTP只允许回环地址。")
    result["scopes"] = " ".join(sorted(set(scopes)))
    return result


@bp.post("/clients")
@admin(write=True)
def create_client(data):
    values = client_data(data)
    if "active" in data and type(data["active"]) is not bool:
        invalid()
    secret = secrets.token_urlsafe(48)
    row = OAuthClient(
        id=secrets.token_urlsafe(24),
        secret_digest=digest(secret),
        active=data.get("active", True),
        version=1,
        **values,
    )
    db.session.add(row)
    db.session.flush()
    audit("client.create", "登记接入应用并生成一次性密钥", row.id)
    return {"client": client_view(row), "credentials": {"clientId": row.id, "clientSecret": secret}}


@bp.post("/clients/<identifier>")
@admin(write=True)
def update_client(data, identifier):
    values = client_data(data)
    if type(data.get("active")) is not bool:
        invalid()
    row = locked(OAuthClient, identifier)
    version(data, row.version)
    if (
        any(getattr(row, key) != value for key, value in values.items())
        or row.active != data["active"]
    ):
        for key, value in values.items():
            setattr(row, key, value)
        row.active = data["active"]
        invalidate(row)
        audit("client.update", "修改应用资料或状态，并撤销旧凭据", row.id)
    return {"client": client_view(row)}


@bp.post("/clients/<identifier>/rotate")
@admin(write=True)
def rotate_client(data, identifier):
    fields(data, set())
    row = locked(OAuthClient, identifier)
    version(data, row.version)
    secret = secrets.token_urlsafe(48)
    row.secret_digest = digest(secret)
    invalidate(row)
    audit("client.rotate", "轮换应用密钥并撤销旧凭据", row.id)
    return {"client": client_view(row), "credentials": {"clientId": row.id, "clientSecret": secret}}


@bp.post("/clients/<identifier>/icon")
@admin(write=True)
def update_icon(data, identifier):
    fields(data, {"image"})
    if "image" not in data:
        invalid()
    row = locked(OAuthClient, identifier)
    version(data, row.version)
    row.icon_key = avatars.save(data["image"]) if data["image"] is not None else None
    invalidate(row)
    audit("client.icon", "更新应用图标并撤销旧凭据", row.id)
    return {"client": client_view(row)}


@public_bp.get("/api/apps/<identifier>/icon/<key>")
def application_icon(identifier, key):
    row = db.session.get(OAuthClient, identifier)
    if not row or not row.active or row.icon_key != key or not avatars.KEY.fullmatch(key):
        raise AuthError("not_found", "图片不存在。", 404)
    path = avatars.directory() / key
    if not path.is_file() or path.is_symlink():
        raise AuthError("not_found", "图片不存在。", 404)
    return send_file(path, mimetype="image/png", conditional=False, max_age=0)


def site_view():
    row = db.session.get(SiteSettings, 1)
    return {
        "name": row.site_name,
        "description": row.description,
        "supportEmail": row.support_email,
    }


def settings_view():
    row = db.session.get(SiteSettings, 1)
    settings = db.session.get(AuthSettings, 1)
    return {
        "siteName": row.site_name,
        "description": row.description,
        "supportEmail": row.support_email,
        "registrationOpen": settings.registration_open,
        "version": row.version,
    }


@bp.get("/settings")
@admin()
def settings():
    return settings_view()


@bp.post("/settings")
@admin(write=True)
def save_settings(data):
    fields(data, {"siteName", "description", "supportEmail", "registrationOpen"})
    row = locked(SiteSettings, 1)
    version(data, row.version)
    for key, maximum in [("siteName", 60), ("description", 200), ("supportEmail", 254)]:
        if (
            not isinstance(data.get(key), str)
            or len(data[key].strip()) > maximum
            or any(ord(c) < 32 for c in data[key])
        ):
            invalid()
    if not data["siteName"].strip() or type(data.get("registrationOpen")) is not bool:
        invalid()
    if data["registrationOpen"] and not db.session.get(MailConfiguration, 1):
        raise AuthError("configuration_required", "请先配置邮件服务，再开启注册。", 409)
    row.site_name = data["siteName"].strip()
    row.description = data["description"].strip()
    row.support_email = email(data["supportEmail"]) if data["supportEmail"].strip() else ""
    row.version += 1
    db.session.get(AuthSettings, 1).registration_open = data["registrationOpen"]
    audit("settings.update", "更新站点资料与注册开关")
    return settings_view()


def mail_view():
    row = db.session.get(MailConfiguration, 1)
    config = mail.configuration() or {}
    return {
        "configured": bool(row),
        "version": row.version if row else 0,
        "host": config.get("host", ""),
        "port": config.get("port", 587),
        "sender": config.get("sender", ""),
        "security": config.get("security", "starttls"),
        "username": config.get("username", ""),
        "passwordConfigured": bool(config.get("password")),
    }


@bp.get("/mail")
@admin()
def read_mail():
    return mail_view()


@bp.post("/mail")
@admin(write=True)
def save_mail(data):
    fields(data, {"host", "port", "sender", "security", "username", "password"})
    old = mail.configuration() or {}
    row = db.session.get(MailConfiguration, 1)
    version(data, row.version if row else 0)
    for key, maximum in [
        ("host", 253),
        ("sender", 254),
        ("security", 16),
        ("username", 254),
        ("password", 512),
    ]:
        if (
            not isinstance(data.get(key, ""), str)
            or len(data.get(key, "")) > maximum
            or any(ord(c) < 32 for c in data.get(key, ""))
        ):
            invalid()
    if type(data.get("port")) is not int or not 1 <= data["port"] <= 65535:
        invalid()
    config = {key: data.get(key, "").strip() for key in ["host", "sender", "security", "username"]}
    config["port"] = data["port"]
    config["sender"] = email(config["sender"])
    config["password"] = data.get("password", "") if config["username"] else ""
    if config["username"] and not config["password"]:
        if (
            config["host"] != old.get("host")
            or config["username"] != old.get("username")
            or not old.get("password")
        ):
            invalid("更换邮件主机或用户名时，请重新填写SMTP密码。")
        config["password"] = old["password"]
    try:
        mail.save_configuration(config, commit=False)
    except (OSError, ValueError):
        raise AuthError("mail_unavailable", "邮件连接或认证未通过，原配置保持不变。", 503) from None
    audit("mail.update", "验证连接并保存加密邮件配置")
    return mail_view()


@bp.post("/mail/test")
@admin(write=True)
def test_mail(data):
    fields(data, {"recipient"})
    recipient = email(data.get("recipient"))
    limit("admin-mail-test", g.auth_session.user_id, maximum=10, seconds=3600)
    mail.send(recipient)
    audit("mail.test", "提交一封测试邮件至指定收件人")
    return {"sent": True}


@bp.get("/audit")
@admin()
def read_audit():
    query = db.select(AdminAudit)
    action = request.args.get("action", "")
    if len(action) > 40:
        invalid()
    if action:
        query = query.where(AdminAudit.action == action)
    return pagination(query, AdminAudit, audit_view)
